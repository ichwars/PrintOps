import csv
import io
from datetime import datetime
from typing import Any

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import OwnershipAccess
from backend.app.core.row_visibility import RowVisibility
from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import INCLUDE_OPEN_RUNS, PrintLogEntry
from backend.app.models.project import Project
from backend.app.services.print_log_run import run_visibility_conditions
from backend.app.services.spool_csv import _sanitize_cell
from backend.app.utils.local_time import to_naive_utc

_RUN_FIELDS = frozenset(
    {
        "print_name",
        "status",
        "quantity",
        "printer_id",
        "printer_name",
        "plate_id",
        "filament_type",
        "filament_used_grams",
        "cost",
        "energy_kwh",
        "energy_cost",
        "failure_reason",
        "user_verdict",
        "duration_seconds",
        "started_at",
        "completed_at",
    }
)


class ExportService:
    """Service for exporting archive data to CSV/Excel formats."""

    # Default fields to export
    DEFAULT_FIELDS = [
        "id",
        "run_id",
        "print_name",
        "filename",
        "status",
        "quantity",
        "printer_id",
        "printer_name",
        "plate_id",
        "project_name",
        "filament_type",
        "filament_used_grams",
        "print_time_seconds",
        "layer_height",
        "nozzle_diameter",
        "bed_temperature",
        "nozzle_temperature",
        "total_layers",
        "cost",
        "designer",
        "tags",
        "notes",
        "failure_reason",
        "user_verdict",
        "duration_seconds",
        "started_at",
        "completed_at",
        "created_at",
    ]

    # Field labels for headers
    FIELD_LABELS = {
        "id": "ID",
        "run_id": "Print ID",
        "printer_name": "Printer",
        "plate_id": "Plate",
        "user_verdict": "Outcome",
        "duration_seconds": "Duration (s)",
        "energy_kwh": "Energy (kWh)",
        "energy_cost": "Energy Cost",
        "print_name": "Print Name",
        "filename": "Filename",
        "status": "Status",
        "quantity": "Items Printed",
        "printer_id": "Printer ID",
        "project_name": "Project",
        "filament_type": "Filament Type",
        "filament_used_grams": "Filament (g)",
        "print_time_seconds": "Print Time (s)",
        "layer_height": "Layer Height (mm)",
        "nozzle_diameter": "Nozzle (mm)",
        "bed_temperature": "Bed Temp (°C)",
        "nozzle_temperature": "Nozzle Temp (°C)",
        "total_layers": "Total Layers",
        "cost": "Cost",
        "designer": "Designer",
        "tags": "Tags",
        "notes": "Notes",
        "failure_reason": "Failure Reason",
        "started_at": "Started At",
        "completed_at": "Completed At",
        "created_at": "Created At",
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    async def export_archives(
        self,
        format: str = "csv",
        fields: list[str] | None = None,
        printer_id: int | None = None,
        project_id: int | None = None,
        status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        search: str | None = None,
        access: OwnershipAccess = OwnershipAccess(None, True),
    ) -> tuple[bytes, str, str]:
        """Export one row for each visible run, or one row for a legacy archive."""
        export_fields = fields if fields else self.DEFAULT_FIELDS
        if any(field not in self.FIELD_LABELS for field in export_fields):
            raise ValueError("Unknown archive export field")

        has_run = PrintLogEntry.id.is_not(None)
        scope = RowVisibility(access.user, access.api_key, access.user is None and access.can_access_all)
        run_printer = case((has_run, PrintLogEntry.printer_id), else_=PrintArchive.printer_id)
        run_project = case((has_run, PrintLogEntry.project_id), else_=PrintArchive.project_id)
        run_status = case((has_run, PrintLogEntry.status), else_=PrintArchive.status)
        run_date = func.coalesce(PrintLogEntry.started_at, PrintLogEntry.created_at, PrintArchive.created_at)
        query = (
            select(PrintArchive, PrintLogEntry, Project.name)
            .outerjoin(PrintLogEntry, PrintLogEntry.archive_id == PrintArchive.id)
            .outerjoin(Project, Project.id == run_project)
            .where(
                PrintArchive.deleted_at.is_(None),
                or_(
                    and_(has_run, *run_visibility_conditions(access)),
                    and_(~has_run, *scope.printer_criteria(PrintArchive.printer_id)),
                ),
            )
            .order_by(run_date.desc(), PrintArchive.id.desc(), PrintLogEntry.id.desc())
            .execution_options(**{INCLUDE_OPEN_RUNS: True})
        )
        if not access.can_access_all:
            if access.user is None:
                raise ValueError("Export has no archive owner")
            query = query.where(PrintArchive.created_by_id == access.user.id)
        if printer_id is not None:
            query = query.where(run_printer == printer_id)
        if project_id is not None:
            query = query.where(run_project == project_id)
        if status:
            query = query.where(run_status.in_([value.strip() for value in status.split(",") if value.strip()]))
        if date_from is not None:
            query = query.where(run_date >= to_naive_utc(date_from))
        if date_to is not None:
            query = query.where(run_date <= to_naive_utc(date_to))
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    PrintArchive.print_name.ilike(pattern),
                    PrintArchive.filename.ilike(pattern),
                    PrintArchive.tags.ilike(pattern),
                    PrintArchive.notes.ilike(pattern),
                    PrintArchive.designer.ilike(pattern),
                    PrintLogEntry.print_name.ilike(pattern),
                )
            )

        rows = [
            self._archive_to_row(archive, run, project, export_fields)
            for archive, run, project in (await self.db.execute(query)).all()
        ]

        # Generate headers
        headers = [self.FIELD_LABELS.get(f, f) for f in export_fields]

        # Generate file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if format == "xlsx":
            file_bytes = self._generate_xlsx(headers, rows, export_fields)
            filename = f"archives_export_{timestamp}.xlsx"
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            file_bytes = self._generate_csv(headers, rows)
            filename = f"archives_export_{timestamp}.csv"
            content_type = "text/csv"

        return file_bytes, filename, content_type

    async def export_stats(
        self,
        format: str = "csv",
        days: int = 30,
        printer_id: int | None = None,
        project_id: int | None = None,
        created_by_id: int | None = None,
        allowed_printer_ids: set[int] | None = None,
        include_unassigned: bool = True,
    ) -> tuple[bytes, str, str]:
        """Export statistics summary to CSV or Excel format.

        Args:
            format: Export format ('csv' or 'xlsx')
            days: Number of days to include in stats
            printer_id: Filter by printer
            project_id: Filter by project
            created_by_id: Filter by user who created the print (-1 for no user)
            allowed_printer_ids: Optional printer scope for the caller.
            include_unassigned: Include printer-less runs when applying a printer scope.

        Returns:
            Tuple of (file_bytes, filename, content_type)
        """
        from backend.app.services.failure_analysis import FailureAnalysisService

        # Get failure analysis data (includes stats)
        analysis_service = FailureAnalysisService(self.db)
        analysis = await analysis_service.analyze_failures(
            days=days,
            printer_id=printer_id,
            project_id=project_id,
            created_by_id=created_by_id,
            allowed_printer_ids=allowed_printer_ids,
            include_unassigned=include_unassigned,
        )

        # Build stats rows
        rows = [
            ["Metric", "Value"],
            ["Period (days)", analysis["period_days"]],
            ["Total Prints", analysis["total_prints"]],
            ["Failed Prints", analysis["failed_prints"]],
            ["Failure Rate (%)", analysis["failure_rate"]],
            [""],
            ["Failures by Reason", ""],
        ]

        for reason, count in analysis["failures_by_reason"].items():
            rows.append([reason, count])

        rows.append([""])
        rows.append(["Failures by Filament", ""])

        for filament, count in analysis["failures_by_filament"].items():
            rows.append([filament, count])

        rows.append([""])
        rows.append(["Failures by Printer", ""])

        for printer, count in analysis["failures_by_printer"].items():
            rows.append([printer, count])

        rows.append([""])
        rows.append(["Weekly Trend", ""])
        rows.append(["Week", "Total", "Failed", "Rate (%)"])

        for week in analysis["trend"]:
            rows.append(
                [
                    week["week_start"],
                    week["total_prints"],
                    week["failed_prints"],
                    week["failure_rate"],
                ]
            )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if format == "xlsx":
            file_bytes = self._generate_xlsx_simple(rows)
            filename = f"stats_export_{timestamp}.xlsx"
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            file_bytes = self._generate_csv_simple(rows)
            filename = f"stats_export_{timestamp}.csv"
            content_type = "text/csv"

        return file_bytes, filename, content_type

    def _archive_to_row(self, archive, run, project, fields: list[str]) -> list[Any]:
        row = []
        for field in fields:
            if field == "project_name":
                value = project
            elif field == "run_id":
                value = run.id if run is not None else None
            elif run is not None and field in _RUN_FIELDS:
                value = getattr(run, field)
            else:
                value = getattr(archive, field, None)
            row.append(value.isoformat() if isinstance(value, datetime) else value)
        return row

    def _generate_csv(self, headers: list[str], rows: list[list]) -> bytes:
        """Generate CSV file content."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows([_sanitize_cell(cell) if isinstance(cell, str) else cell for cell in row] for row in rows)
        return output.getvalue().encode("utf-8")

    def _generate_csv_simple(self, rows: list[list]) -> bytes:
        """Generate CSV file content from simple rows (no separate headers)."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(rows)
        return output.getvalue().encode("utf-8")

    def _generate_xlsx(self, headers: list[str], rows: list[list], fields: list[str]) -> bytes:
        """Generate Excel file content."""
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
            from openpyxl.utils import get_column_letter
        except ImportError:
            raise ImportError("openpyxl is required for Excel export. Install with: pip install openpyxl")

        wb = Workbook()
        ws = wb.active
        ws.title = "Archives"

        # Header style
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_alignment = Alignment(horizontal="center")

        # Write headers
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment

        # Write data
        for row_idx, row in enumerate(rows, 2):
            for col_idx, value in enumerate(row, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                if isinstance(value, str):
                    cell.data_type = "s"

        # Auto-adjust column widths
        for col_idx, _field in enumerate(fields, 1):
            column_letter = get_column_letter(col_idx)
            max_length = len(headers[col_idx - 1])
            for row in rows:
                cell_value = row[col_idx - 1]
                if cell_value is not None:
                    max_length = max(max_length, len(str(cell_value)))
            ws.column_dimensions[column_letter].width = min(max_length + 2, 50)

        # Freeze header row
        ws.freeze_panes = "A2"

        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()

    def _generate_xlsx_simple(self, rows: list[list]) -> bytes:
        """Generate Excel file content from simple rows."""
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font
        except ImportError:
            raise ImportError("openpyxl is required for Excel export. Install with: pip install openpyxl")

        wb = Workbook()
        ws = wb.active
        ws.title = "Statistics"

        bold_font = Font(bold=True)

        for row_idx, row in enumerate(rows, 1):
            for col_idx, value in enumerate(row, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                # Bold section headers
                if col_idx == 1 and value and isinstance(value, str) and value.endswith(":"):
                    cell.font = bold_font

        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()
