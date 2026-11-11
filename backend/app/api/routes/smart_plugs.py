"""API routes for smart plug management."""

import logging

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.routes.settings import get_homeassistant_settings, get_setting
from backend.app.core.auth import (
    OwnershipAccess,
    RequirePermissionIfAuthEnabled,
    caller_is_api_key,
    require_permission_with_key,
)
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.core.printer_associations import delete_smart_plug_rows
from backend.app.core.row_visibility import resolve_printer_visibility
from backend.app.core.tasks import spawn_background_task
from backend.app.core.user_printer_scope import prepare_printer_scope_write
from backend.app.models.equipment import Equipment
from backend.app.models.printer import Printer
from backend.app.models.smart_plug import SmartPlug
from backend.app.models.user import User
from backend.app.schemas.smart_plug import (
    HAEntity,
    HASensorEntity,
    HATestConnectionRequest,
    HATestConnectionResponse,
    RESTTestConnectionRequest,
    RESTTestConnectionResponse,
    SmartPlugBase,
    SmartPlugControl,
    SmartPlugCreate,
    SmartPlugEnergy,
    SmartPlugResponse,
    SmartPlugStatus,
    SmartPlugTestConnection,
    SmartPlugUpdate,
)
from backend.app.services.discovery import tasmota_scanner
from backend.app.services.homeassistant import homeassistant_service
from backend.app.services.mqtt_relay import mqtt_relay
from backend.app.services.mqtt_smart_plug import subscribe_plug_to_mqtt
from backend.app.services.plug_energy_history import fill_derived_energy
from backend.app.services.printer_manager import printer_manager
from backend.app.services.rest_smart_plug import rest_smart_plug_service
from backend.app.services.secret_fields import (
    REST_PLUG_URLS,
    SECRET_PLACEHOLDER,
    SMART_PLUG_SECRETS,
    SecretConfigError,
    lock_settings_credentials,
    merge_secret_update,
    reject_placeholder,
    same_value,
    secret_is_set,
)
from backend.app.services.smart_plug_manager import smart_plug_manager
from backend.app.services.smart_plug_selection import (
    can_be_switched,
    pick_power_plug,
    plugs_for_printer,
)
from backend.app.services.tasmota import tasmota_service
from backend.app.utils.local_time import utcnow_naive

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/smart-plugs", tags=["smart-plugs"])

_PRIVATE_PLUG_FIELDS = (
    "password",
    "rest_headers",
    "rest_on_url",
    "rest_on_body",
    "rest_off_url",
    "rest_off_body",
    "rest_status_url",
    "rest_power_url",
    "rest_energy_url",
)


def _plug_response(plug: SmartPlug, user: User | None, is_api_key: bool) -> SmartPlugResponse:
    response = SmartPlugResponse.model_validate(plug)
    if not is_api_key and (user is None or user.has_permission(Permission.SMART_PLUGS_UPDATE.value)):
        return response
    return response.model_copy(update=dict.fromkeys(_PRIVATE_PLUG_FIELDS))


_PLUG_CREDENTIAL_FIELDS = frozenset(SMART_PLUG_SECRETS) | frozenset(
    field for destinations in SMART_PLUG_SECRETS.values() for field in destinations
)


def _require_saved_secret_permission(access: OwnershipAccess, permission: Permission) -> None:
    if access.api_key is not None or (access.user is not None and not access.user.has_permission(permission.value)):
        raise HTTPException(403, f"Testing a saved secret requires {permission.value}")


async def _plug_for_secret_test(
    db: AsyncSession, plug_id: int | None, plug_type: str, access: OwnershipAccess
) -> SmartPlug:
    _require_saved_secret_permission(access, Permission.SMART_PLUGS_UPDATE)
    if plug_id is None:
        raise HTTPException(400, "Enter the secret because no plug is selected")
    plug = await db.get(SmartPlug, plug_id)
    if plug is None or plug.plug_type != plug_type or not access.allows_printer(plug.printer_id):
        raise HTTPException(404, "Smart plug not found")
    return plug


async def _validate_link_target(
    db: AsyncSession,
    *,
    printer_id: int | None,
    equipment_id: int | None,
    plug_type: str,
    current_plug_id: int | None = None,
    check_unique: bool = True,
) -> None:
    if printer_id is not None and equipment_id is not None:
        raise HTTPException(400, "A smart plug can only be linked to one target")

    if printer_id is not None:
        result = await db.execute(select(Printer.id).where(Printer.id == printer_id).with_for_update())
        if result.scalar_one_or_none() is None:
            raise HTTPException(400, "Printer not found")

        if plug_type == "tasmota" and check_unique:
            query = select(SmartPlug.id).where(
                SmartPlug.printer_id == printer_id,
                SmartPlug.plug_type == "tasmota",
            )
            if current_plug_id is not None:
                query = query.where(SmartPlug.id != current_plug_id)
            if await db.scalar(query.limit(1)) is not None:
                raise HTTPException(400, "This printer already has a Tasmota plug assigned")

    if equipment_id:
        result = await db.execute(
            select(Equipment).where(
                Equipment.id == equipment_id,
                Equipment.equipment_type == "dryer",
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(400, "Filament dryer not found")

        if plug_type == "tasmota" and check_unique:
            query = select(SmartPlug.id).where(
                SmartPlug.equipment_id == equipment_id,
                SmartPlug.plug_type == "tasmota",
            )
            if current_plug_id is not None:
                query = query.where(SmartPlug.id != current_plug_id)
            if await db.scalar(query.limit(1)) is not None:
                raise HTTPException(400, "This filament dryer already has a Tasmota plug assigned")


@router.get("/", response_model=list[SmartPlugResponse])
async def list_smart_plugs(
    db: AsyncSession = DB_SESSION,
    user: User | None = RequirePermissionIfAuthEnabled(Permission.SMART_PLUGS_READ),
    is_api_key: bool = Depends(caller_is_api_key),
):
    """List all smart plugs."""
    result = await db.execute(select(SmartPlug).order_by(SmartPlug.name))
    return [_plug_response(plug, user, is_api_key) for plug in result.scalars().all()]


@router.post("/", response_model=SmartPlugResponse)
async def create_smart_plug(
    data: SmartPlugCreate,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SMART_PLUGS_CREATE),
):
    """Create a new smart plug."""
    try:
        reject_placeholder({field: getattr(data, field) for field in SMART_PLUG_SECRETS})
    except SecretConfigError as exc:
        raise HTTPException(400, str(exc)) from None
    if data.printer_id is not None:
        await prepare_printer_scope_write(db)
    await _validate_link_target(
        db,
        printer_id=data.printer_id,
        equipment_id=data.equipment_id,
        plug_type=data.plug_type,
    )

    # For MQTT plugs, ensure MQTT broker is configured and service is connected
    if data.plug_type == "mqtt":
        # Try to configure the smart plug service if not already configured
        if not mqtt_relay.smart_plug_service.is_configured():
            # Get MQTT broker settings from database
            mqtt_broker = await get_setting(db, "mqtt_broker") or ""
            if not mqtt_broker:
                raise HTTPException(
                    400,
                    "MQTT broker not configured. Please set MQTT broker address in Settings → Network → MQTT Publishing.",
                )

            # Configure the smart plug service with broker settings
            mqtt_settings = {
                "mqtt_enabled": True,  # Enable for smart plug subscription
                "mqtt_broker": mqtt_broker,
                "mqtt_port": int(await get_setting(db, "mqtt_port") or "1883"),
                "mqtt_username": await get_setting(db, "mqtt_username") or "",
                "mqtt_password": await get_setting(db, "mqtt_password") or "",
                "mqtt_use_tls": (await get_setting(db, "mqtt_use_tls") or "false") == "true",
            }
            await mqtt_relay.smart_plug_service.configure(mqtt_settings)

            # Check if connection succeeded
            if not mqtt_relay.smart_plug_service.is_configured():
                raise HTTPException(
                    400,
                    f"Failed to connect to MQTT broker at {mqtt_broker}. Please check your MQTT settings.",
                )

    plug_data = data.model_dump()

    # For HA entities, default auto_on and auto_off to False
    # (they're for automations, not power control like Tasmota plugs)
    if data.plug_type == "homeassistant":
        plug_data["auto_on"] = False
        plug_data["auto_off"] = False

    plug = SmartPlug(**plug_data)
    db.add(plug)
    await db.commit()
    await db.refresh(plug)

    # Subscribe MQTT plugs to their topics
    if plug.plug_type == "mqtt":
        topics = subscribe_plug_to_mqtt(mqtt_relay.smart_plug_service, plug)
        if topics:
            logger.info("Created MQTT plug '%s' subscribed to %s", plug.name, ", ".join(topics))
    elif plug.plug_type == "homeassistant":
        logger.info("Created Home Assistant plug '%s' (%s)", plug.name, plug.ha_entity_id)
    else:
        logger.info("Created Tasmota plug '%s' at %s", plug.name, plug.ip_address)
    return plug


@router.get("/by-printer/{printer_id}", response_model=SmartPlugResponse | None)
async def get_smart_plug_by_printer(
    printer_id: int,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.SMART_PLUGS_READ)),
    is_api_key: bool = Depends(caller_is_api_key),
):
    """Get the linked row that best represents the printer's power supply."""
    visibility = await resolve_printer_visibility(db, access, Permission.SMART_PLUGS_READ, printer_id)
    plug = pick_power_plug(await plugs_for_printer(db, printer_id))
    return _plug_response(plug, visibility.user, is_api_key) if plug else None


@router.get("/by-printer/{printer_id}/scripts", response_model=list[SmartPlugResponse])
async def get_script_plugs_by_printer(
    printer_id: int,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.SMART_PLUGS_READ)),
    is_api_key: bool = Depends(caller_is_api_key),
):
    """Get all HA entities assigned to a printer for display on printer card.

    Returns HA entities (switches, scripts, lights, etc.) for the printer that have
    show_on_printer_card enabled.
    Used to display action buttons alongside the main power plug.
    """
    visibility = await resolve_printer_visibility(db, access, Permission.SMART_PLUGS_READ, printer_id)
    plugs = await plugs_for_printer(db, printer_id)
    return card_script_plugs(plugs, visibility.user, is_api_key)


def card_script_plugs(plugs: list[SmartPlug], user: User | None, is_api_key: bool) -> list[SmartPlugResponse]:
    main_plug = pick_power_plug(plugs)
    duplicate_id = main_plug.id if main_plug and can_be_switched(main_plug) else None

    # A switchable main entity is already rendered in the Power row. Scripts
    # remain here even in the script-only fallback so their one-click action is
    # preserved.
    ha_entities = [
        plug
        for plug in plugs
        if plug.plug_type == "homeassistant"
        and plug.ha_entity_id
        and plug.show_on_printer_card
        and plug.id != duplicate_id
    ]
    return [_plug_response(plug, user, is_api_key) for plug in ha_entities]


# Tasmota Discovery Endpoints
# NOTE: These must be defined BEFORE /{plug_id} routes to avoid path conflicts


class TasmotaScanRequest(BaseModel):
    """Request to scan for Tasmota devices."""

    from_ip: str | None = None  # Starting IP (auto-detected if not provided)
    to_ip: str | None = None  # Ending IP (auto-detected if not provided)
    timeout: float = 1.0  # Connection timeout per host


def get_local_network_range() -> tuple[str, str]:
    """Auto-detect local network and return IP range to scan."""
    import socket

    try:
        # Get local IP by connecting to a public DNS (doesn't actually send data)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()

        # Parse IP and create range (assume /24 subnet)
        parts = local_ip.split(".")
        base = ".".join(parts[:3])
        from_ip = f"{base}.1"
        to_ip = f"{base}.254"

        logger.info("Auto-detected network: %s - %s (local IP: %s)", from_ip, to_ip, local_ip)
        return from_ip, to_ip

    except OSError as e:
        logger.error("Failed to detect local network: %s", e)
        # Fallback to common home network
        return "192.168.1.1", "192.168.1.254"


class TasmotaScanStatus(BaseModel):
    """Tasmota scan status response."""

    running: bool
    scanned: int
    total: int


class DiscoveredTasmotaDevice(BaseModel):
    """Discovered Tasmota device."""

    ip_address: str
    name: str
    module: int | None = None
    state: str | None = None
    discovered_at: str | None = None


@router.post("/discover/scan", response_model=TasmotaScanStatus)
async def start_tasmota_scan(
    request: TasmotaScanRequest | None = Body(default=None),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SMART_PLUGS_CREATE),
):
    """Start an IP range scan for Tasmota devices.

    Auto-detects local network if no IP range provided.
    """

    # Auto-detect network
    from_ip, to_ip = get_local_network_range()
    timeout = request.timeout if request else 1.0

    # Start scan in background
    spawn_background_task(
        tasmota_scanner.scan_range(from_ip, to_ip, timeout),
        name="tasmota-scan",
    )

    # Return immediate status
    scanned, total = tasmota_scanner.progress
    return TasmotaScanStatus(
        running=tasmota_scanner.is_running,
        scanned=scanned,
        total=total,
    )


@router.get("/discover/status", response_model=TasmotaScanStatus)
async def get_tasmota_scan_status(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SMART_PLUGS_READ),
):
    """Get the current Tasmota scan status."""
    scanned, total = tasmota_scanner.progress
    return TasmotaScanStatus(
        running=tasmota_scanner.is_running,
        scanned=scanned,
        total=total,
    )


@router.post("/discover/stop", response_model=TasmotaScanStatus)
async def stop_tasmota_scan(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SMART_PLUGS_CREATE),
):
    """Stop the current Tasmota scan."""
    tasmota_scanner.stop()
    scanned, total = tasmota_scanner.progress
    return TasmotaScanStatus(
        running=tasmota_scanner.is_running,
        scanned=scanned,
        total=total,
    )


@router.get("/discover/devices", response_model=list[DiscoveredTasmotaDevice])
async def get_discovered_tasmota_devices(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SMART_PLUGS_READ),
):
    """Get list of discovered Tasmota devices."""
    return [
        DiscoveredTasmotaDevice(
            ip_address=d["ip_address"],
            name=d["name"],
            module=d.get("module"),
            state=d.get("state"),
            discovered_at=d.get("discovered_at"),
        )
        for d in tasmota_scanner.discovered_devices
    ]


# Home Assistant Discovery Endpoints


@router.post("/ha/test-connection", response_model=HATestConnectionResponse)
async def test_ha_connection(
    request: HATestConnectionRequest,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.SMART_PLUGS_CONTROL)),
):
    """Test Home Assistant, binding a saved token to its configured URL."""
    token = request.token
    if token == SECRET_PLACEHOLDER:
        _require_saved_secret_permission(access, Permission.SETTINGS_UPDATE)
        stored = await get_homeassistant_settings(db)
        token = stored["ha_token"]
        if not secret_is_set(token):
            raise HTTPException(400, "Enter the token because none is saved")
        if not same_value(request.url, stored["ha_url"]):
            raise HTTPException(400, "Enter the token again because the URL changed")
    result = await homeassistant_service.test_connection(request.url, token)
    return HATestConnectionResponse(**result)


@router.post("/rest/test-connection", response_model=RESTTestConnectionResponse)
async def test_rest_connection(
    request: RESTTestConnectionRequest,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.SMART_PLUGS_UPDATE)),
):
    """Test a REST endpoint with headers bound to the saved plug's destinations."""
    headers = request.headers
    if headers == SECRET_PLACEHOLDER:
        plug = await _plug_for_secret_test(db, request.plug_id, "rest", access)
        headers = plug.rest_headers
        if not secret_is_set(headers):
            raise HTTPException(400, "Enter the headers because none are saved")
        if not any(same_value(request.url, getattr(plug, field)) for field in REST_PLUG_URLS):
            raise HTTPException(400, "Enter the headers again because the URL changed")
    result = await rest_smart_plug_service.test_connection(request.url, request.method, headers)
    return RESTTestConnectionResponse(**result)


@router.get("/ha/entities", response_model=list[HAEntity])
async def list_ha_entities(
    db: AsyncSession = DB_SESSION,
    search: str | None = None,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SMART_PLUGS_READ),
):
    """List available Home Assistant entities.

    By default, returns switch/light/input_boolean entities.
    When search is provided, searches ALL entities by entity_id or friendly_name.

    Requires HA connection settings to be configured in Settings.
    """
    from backend.app.api.routes.settings import get_homeassistant_settings

    ha_settings = await get_homeassistant_settings(db)
    ha_url = ha_settings["ha_url"]
    ha_token = ha_settings["ha_token"]

    if not ha_url or not ha_token:
        raise HTTPException(
            400, "Home Assistant not configured. Please set HA URL and token in Settings → Network → Home Assistant."
        )

    entities = await homeassistant_service.list_entities(ha_url, ha_token, search)
    return [HAEntity(**e) for e in entities]


@router.get("/ha/sensors", response_model=list[HASensorEntity])
async def list_ha_sensor_entities(
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SMART_PLUGS_READ),
):
    """List available Home Assistant sensor entities for energy monitoring.

    Returns sensors with power/energy units (W, kW, kWh, Wh).
    Requires HA connection settings to be configured in Settings.
    """
    from backend.app.api.routes.settings import get_homeassistant_settings

    ha_settings = await get_homeassistant_settings(db)
    ha_url = ha_settings["ha_url"]
    ha_token = ha_settings["ha_token"]

    if not ha_url or not ha_token:
        raise HTTPException(
            400, "Home Assistant not configured. Please set HA URL and token in Settings → Network → Home Assistant."
        )

    sensors = await homeassistant_service.list_sensor_entities(ha_url, ha_token)
    return [HASensorEntity(**s) for s in sensors]


@router.get("/{plug_id}", response_model=SmartPlugResponse)
async def get_smart_plug(
    plug_id: int,
    db: AsyncSession = DB_SESSION,
    user: User | None = RequirePermissionIfAuthEnabled(Permission.SMART_PLUGS_READ),
    is_api_key: bool = Depends(caller_is_api_key),
):
    """Get a specific smart plug."""
    result = await db.execute(select(SmartPlug).where(SmartPlug.id == plug_id))
    plug = result.scalar_one_or_none()
    if not plug:
        raise HTTPException(404, "Smart plug not found")
    return _plug_response(plug, user, is_api_key)


@router.patch("/{plug_id}", response_model=SmartPlugResponse)
async def update_smart_plug(
    plug_id: int,
    data: SmartPlugUpdate,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SMART_PLUGS_UPDATE),
):
    """Update a smart plug."""
    await prepare_printer_scope_write(db)
    update_data = data.model_dump(exclude_unset=True)
    if update_data.keys() & _PLUG_CREDENTIAL_FIELDS:
        await lock_settings_credentials(db)
    result = await db.execute(select(SmartPlug).where(SmartPlug.id == plug_id))
    plug = result.scalar_one_or_none()
    if not plug:
        raise HTTPException(404, "Smart plug not found")

    if update_data.keys() & _PLUG_CREDENTIAL_FIELDS:
        stored = {field: getattr(plug, field) for field in _PLUG_CREDENTIAL_FIELDS}
        try:
            update_data = merge_secret_update(stored, update_data, SMART_PLUG_SECRETS)
        except SecretConfigError as exc:
            raise HTTPException(400, str(exc)) from None

    target_printer_id = update_data.get("printer_id", plug.printer_id)
    target_equipment_id = update_data.get("equipment_id", plug.equipment_id)
    target_plug_type = update_data.get("plug_type", plug.plug_type)
    printer_changed = target_printer_id != plug.printer_id
    await _validate_link_target(
        db,
        printer_id=target_printer_id,
        equipment_id=target_equipment_id,
        plug_type=target_plug_type,
        current_plug_id=plug_id,
        check_unique=printer_changed or target_equipment_id != plug.equipment_id or target_plug_type != plug.plug_type,
    )

    merged = {field: update_data.get(field, getattr(plug, field)) for field in SmartPlugBase.model_fields}
    try:
        SmartPlugBase.model_validate(merged)
    except ValidationError as error:
        raise RequestValidationError(
            [
                {"type": issue["type"], "loc": ("body", *issue["loc"]), "msg": issue["msg"]}
                for issue in error.errors(include_url=False, include_input=False, include_context=False)
            ]
        ) from None

    # Track old MQTT settings for comparison
    old_plug_type = plug.plug_type
    old_mqtt_config = {
        "power_topic": plug.mqtt_power_topic or plug.mqtt_topic,
        "power_path": plug.mqtt_power_path,
        "power_multiplier": plug.mqtt_power_multiplier,
        "energy_topic": plug.mqtt_energy_topic or plug.mqtt_topic,
        "energy_path": plug.mqtt_energy_path,
        "energy_multiplier": plug.mqtt_energy_multiplier,
        "state_topic": plug.mqtt_state_topic or plug.mqtt_topic,
        "state_path": plug.mqtt_state_path,
        "state_on_value": plug.mqtt_state_on_value,
    }

    for field, value in update_data.items():
        setattr(plug, field, value)

    if printer_changed:
        smart_plug_manager.cancel_pending_off(plug.id)
        plug.auto_off_pending = False
        plug.auto_off_pending_since = None

    await db.commit()
    await db.refresh(plug)

    # Handle MQTT subscription changes
    if old_plug_type == "mqtt" and plug.plug_type != "mqtt":
        # Changed away from MQTT - unsubscribe
        mqtt_relay.smart_plug_service.unsubscribe(plug.id)
    elif plug.plug_type == "mqtt":
        # Check if any MQTT config changed
        new_mqtt_config = {
            "power_topic": plug.mqtt_power_topic or plug.mqtt_topic,
            "power_path": plug.mqtt_power_path,
            "power_multiplier": plug.mqtt_power_multiplier,
            "energy_topic": plug.mqtt_energy_topic or plug.mqtt_topic,
            "energy_path": plug.mqtt_energy_path,
            "energy_multiplier": plug.mqtt_energy_multiplier,
            "state_topic": plug.mqtt_state_topic or plug.mqtt_topic,
            "state_path": plug.mqtt_state_path,
            "state_on_value": plug.mqtt_state_on_value,
        }

        mqtt_changed = old_plug_type != "mqtt" or old_mqtt_config != new_mqtt_config

        if mqtt_changed:
            # Unsubscribe from old topics first
            if old_plug_type == "mqtt":
                mqtt_relay.smart_plug_service.unsubscribe(plug.id)

            # Subscribe via the shared helper (matches startup restore and
            # create route) — keeps all three paths in lock-step.
            subscribe_plug_to_mqtt(mqtt_relay.smart_plug_service, plug)

    logger.info("Updated smart plug '%s'", plug.name)
    return plug


@router.delete("/{plug_id}")
async def delete_smart_plug(
    plug_id: int,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SMART_PLUGS_DELETE),
):
    """Delete a smart plug."""
    result = await db.execute(select(SmartPlug).where(SmartPlug.id == plug_id))
    plug = result.scalar_one_or_none()
    if not plug:
        raise HTTPException(404, "Smart plug not found")

    plug_name = plug.name
    plug_type = plug.plug_type

    await delete_smart_plug_rows(db, plug_id)
    await db.commit()
    forget_deleted_smart_plug(plug_id, plug_type)

    logger.info("Deleted smart plug '%s'", plug_name)
    return {"message": "Smart plug deleted"}


def forget_deleted_smart_plug(plug_id: int, plug_type: str) -> None:
    from backend.app.services.smart_plug_manager import smart_plug_manager

    smart_plug_manager.forget_plug(plug_id)
    if plug_type == "mqtt":
        mqtt_relay.smart_plug_service.unsubscribe(plug_id)


async def _get_service_for_plug(plug: SmartPlug, db: AsyncSession):
    """Get the appropriate service for the plug type.

    For HA plugs, configures the service with current settings from DB.
    """
    if plug.plug_type == "homeassistant":
        # Configure HA service with current settings
        from backend.app.api.routes.settings import get_homeassistant_settings

        ha_settings = await get_homeassistant_settings(db)
        homeassistant_service.configure(ha_settings["ha_url"], ha_settings["ha_token"])
        return homeassistant_service
    if plug.plug_type == "rest":
        return rest_smart_plug_service
    return tasmota_service


@router.post("/{plug_id}/control")
async def control_smart_plug(
    plug_id: int,
    control: SmartPlugControl,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SMART_PLUGS_CONTROL),
):
    """Manual control: on/off/toggle."""
    result = await db.execute(select(SmartPlug).where(SmartPlug.id == plug_id))
    plug = result.scalar_one_or_none()
    if not plug:
        raise HTTPException(404, "Smart plug not found")

    # MQTT plugs are monitor-only - cannot control them
    if plug.plug_type == "mqtt":
        raise HTTPException(
            400,
            "MQTT plugs are monitor-only. Use your MQTT broker or home automation system to control them.",
        )

    service = await _get_service_for_plug(plug, db)

    if control.action == "on":
        success = await service.turn_on(plug)
        expected_state = "ON"
    elif control.action == "off":
        success = await service.turn_off(plug)
        expected_state = "OFF"
    elif control.action == "toggle":
        success = await service.toggle(plug)
        expected_state = None
        if success:
            try:
                status = await service.get_status(plug)
                if status.get("reachable") and status.get("state") in {"ON", "OFF"}:
                    expected_state = status["state"]
            except Exception:
                logger.debug("Could not read toggled plug %s", plug_id, exc_info=True)
    else:
        raise HTTPException(400, f"Invalid action: {control.action}")

    if not success:
        raise HTTPException(503, "Failed to communicate with device")

    # Update last state and reset auto_off_executed when turning on
    if expected_state:
        plug.last_state = expected_state
        if expected_state == "ON":
            plug.auto_off_executed = False  # Reset flag when manually turning on
        elif expected_state == "OFF" and plug.printer_id and plug.controls_printer_power:
            # Mark printer offline immediately for faster UI update
            printer_manager.mark_printer_offline(plug.printer_id)
    plug.last_checked = utcnow_naive()
    await db.commit()

    if expected_state is not None:
        await smart_plug_manager.on_plug_switched(plug, expected_state == "ON", db, automatic=False)
    return {"success": True, "action": control.action}


@router.get("/{plug_id}/status", response_model=SmartPlugStatus)
async def get_plug_status(
    plug_id: int,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SMART_PLUGS_READ),
):
    """Get current plug status from device including energy data."""
    result = await db.execute(select(SmartPlug).where(SmartPlug.id == plug_id))
    plug = result.scalar_one_or_none()
    if not plug:
        raise HTTPException(404, "Smart plug not found")

    # Handle MQTT plugs - get data from subscription service
    if plug.plug_type == "mqtt":
        data = mqtt_relay.smart_plug_service.get_plug_data(plug_id)
        is_reachable = mqtt_relay.smart_plug_service.is_reachable(plug_id)

        if data:
            # Update last state in database
            if is_reachable and data.state:
                plug.last_state = data.state
                plug.last_checked = utcnow_naive()
                await db.commit()

            energy_data = None
            if data.power is not None or data.energy is not None:
                energy = {
                    "power": data.power,
                    "today": data.energy,
                }
                energy = await fill_derived_energy(db, plug.id, energy)
                energy_data = SmartPlugEnergy(
                    **energy,
                )

            return SmartPlugStatus(
                state=data.state,
                reachable=is_reachable,
                device_name=None,
                energy=energy_data,
            )

        # No data received yet
        return SmartPlugStatus(
            state=None,
            reachable=False,
            device_name=None,
            energy=None,
        )

    # Handle Tasmota/HomeAssistant plugs
    service = await _get_service_for_plug(plug, db)
    status = await service.get_status(plug)

    # Update last state in database
    if status["reachable"]:
        plug.last_state = status["state"]
        plug.last_checked = utcnow_naive()
        await db.commit()

    # Fetch energy data if device is reachable
    energy_data = None
    if status["reachable"]:
        energy = await service.get_energy(plug)
        if energy:
            energy = await fill_derived_energy(db, plug.id, energy)
            energy_data = SmartPlugEnergy(**energy)

    return SmartPlugStatus(
        state=status["state"],
        reachable=status["reachable"],
        device_name=status.get("device_name"),
        energy=energy_data,
    )


@router.post("/test-connection")
async def test_connection(
    data: SmartPlugTestConnection,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.SMART_PLUGS_CONTROL)),
):
    """Test a Tasmota device with its password bound to its address."""
    password = data.password
    if password == SECRET_PLACEHOLDER:
        plug = await _plug_for_secret_test(db, data.plug_id, "tasmota", access)
        password = plug.password
        if not secret_is_set(password):
            raise HTTPException(400, "Enter the password because none is saved")
        if not same_value(data.ip_address, plug.ip_address):
            raise HTTPException(400, "Enter the password again because the address changed")
    result = await tasmota_service.test_connection(data.ip_address, data.username, password)

    if not result["success"]:
        raise HTTPException(503, result.get("error", "Failed to connect to device"))

    return {
        "success": True,
        "state": result["state"],
        "device_name": result.get("device_name"),
    }
