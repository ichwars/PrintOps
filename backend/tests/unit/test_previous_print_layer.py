"""A new print never inherits the previous print's last layer."""

import pytest


class TestPreviousPrintLayerIgnored:
    """#3317: right after a print starts, an H2S sent one frame carrying the
    previous print's last layer (`layer_num` 357, `mc_percent` 0), then 0. The
    0 saved 357 as the new print's last layer, so a print failing at layer 0
    was charged to Spoolman as if it had finished.
    """

    FILE = "/data/Metadata/plate_1.gcode"

    @pytest.fixture
    def mqtt_client(self):
        from backend.app.services.bambu_mqtt import BambuMQTTClient

        client = BambuMQTTClient(
            ip_address="192.168.1.100",
            serial_number="TEST123",
            access_code="12345678",
        )
        client.on_print_start = lambda data: None
        client.layer_changes = []
        client.on_layer_change = client.layer_changes.append
        client.completions = []
        client.on_print_complete = client.completions.append
        return client

    def _finished_previous_print(self, client, layers: int):
        client._previous_gcode_state = "FINISH"
        client._previous_gcode_file = self.FILE
        client._was_running = False
        client.state.state = "FINISH"
        client.state.gcode_file = self.FILE
        client.state.layer_num = layers
        client.state.total_layers = layers

    def _start(self, client):
        client._process_message({"print": {"gcode_state": "RUNNING", "gcode_file": self.FILE, "subtask_name": "t"}})

    def _fail(self, client) -> dict:
        client._process_message({"print": {"gcode_state": "FAILED", "gcode_file": self.FILE}})
        assert len(client.completions) == 1
        return client.completions[0]

    def test_failure_before_first_layer_reports_layer_zero(self, mqtt_client):
        # The 2026-10-14 sequence from the report: same layer count as before.
        self._finished_previous_print(mqtt_client, 357)
        self._start(mqtt_client)
        mqtt_client._process_message({"print": {"layer_num": 357, "total_layer_num": 357, "mc_percent": 0}})
        assert mqtt_client.state.layer_num == 0
        mqtt_client._process_message({"print": {"layer_num": 0}})

        assert self._fail(mqtt_client)["last_layer_num"] == 0
        assert mqtt_client.layer_changes == []

    def test_stale_layer_above_new_total_is_ignored(self, mqtt_client):
        # The 2026-10-13 sequence: 357 from the previous print, 55 for this one.
        self._finished_previous_print(mqtt_client, 357)
        self._start(mqtt_client)
        mqtt_client._process_message({"print": {"layer_num": 357, "total_layer_num": 55, "mc_percent": 0}})
        mqtt_client._process_message({"print": {"layer_num": 0}})

        assert mqtt_client.state.layer_num == 0
        assert mqtt_client.state.total_layers == 55
        assert self._fail(mqtt_client)["last_layer_num"] == 0

    def test_new_print_can_reach_the_previous_last_layer(self, mqtt_client):
        # Once the print reports a layer of its own, the old value is just a
        # layer number again.
        self._finished_previous_print(mqtt_client, 3)
        self._start(mqtt_client)
        for layer in (3, 0, 1, 2, 3, 4):
            mqtt_client._process_message({"print": {"layer_num": layer}})
        assert mqtt_client.state.layer_num == 4
        mqtt_client._process_message({"print": {"layer_num": 0}})

        assert self._fail(mqtt_client)["last_layer_num"] == 4
        assert mqtt_client.layer_changes == [1, 2, 3, 4]

    def test_previous_print_ending_on_layer_one_does_not_hide_layer_one(self, mqtt_client):
        # A one-layer print printed again: its own layer 1 is the only layer it
        # reports, so it must not be taken for the previous print's.
        self._finished_previous_print(mqtt_client, 1)
        self._start(mqtt_client)
        mqtt_client._process_message({"print": {"layer_num": 1, "total_layer_num": 1}})
        assert mqtt_client.state.layer_num == 1
        mqtt_client._process_message({"print": {"layer_num": 0}})

        assert self._fail(mqtt_client)["last_layer_num"] == 1
        assert mqtt_client.layer_changes == [1]

    def test_cancel_mid_print_still_keeps_last_layer(self, mqtt_client):
        # The firmware's reset-to-0 on cancel is what `_last_valid_layer_num`
        # exists for; the guard must not get in its way.
        self._finished_previous_print(mqtt_client, 0)
        self._start(mqtt_client)
        for layer in (1, 2, 50):
            mqtt_client._process_message({"print": {"layer_num": layer}})
        mqtt_client._process_message({"print": {"layer_num": 0}})

        assert self._fail(mqtt_client)["last_layer_num"] == 50
