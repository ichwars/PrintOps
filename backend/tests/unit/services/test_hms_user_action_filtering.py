import pytest


class TestHMSUserActionFiltering:
    """HMS short codes the printer firmware emits during user-cancel sequences
    must not appear in state.hms_errors — they're status echoes, not faults,
    and shouldn't drive the printer card's "X problem" badge or red pip."""

    @pytest.fixture
    def mqtt_client(self):
        from backend.app.services.bambu_mqtt import BambuMQTTClient

        return BambuMQTTClient(
            ip_address="192.168.1.100",
            serial_number="TEST_HMS",
            access_code="12345678",
        )

    def test_task_cancelled_echo_0300_400c_filtered(self, mqtt_client):
        """0300_400C ("The task was canceled.") is the user-cancel echo that was
        leaving the printer card stuck on "1 problem" after every stop."""
        mqtt_client._update_state({"hms": [{"attr": 0x03000300, "code": 0x400C}]})
        assert mqtt_client.state.hms_errors == []

    def test_printing_cancelled_echo_0500_400e_filtered(self, mqtt_client):
        """0500_400E ("Printing was cancelled.") — the corresponding nozzle-module
        echo that the backend notification path was already suppressing for the
        same reason."""
        mqtt_client._update_state({"hms": [{"attr": 0x05000300, "code": 0x400E}]})
        assert mqtt_client.state.hms_errors == []

    def test_real_layer_shift_still_passes_through(self, mqtt_client):
        """0300_4057 (Z-axis step loss) is a real fault and must NOT be filtered."""
        mqtt_client._update_state({"hms": [{"attr": 0x03000100, "code": 0x4057}]})
        assert len(mqtt_client.state.hms_errors) == 1
        assert mqtt_client.state.hms_errors[0].code == "0x4057"

    def test_filter_only_drops_user_action_codes_keeps_concurrent_real_faults(self, mqtt_client):
        """When the user cancels mid-fault, the firmware sends the real fault HMS
        alongside the cancel echo. Drop only the echo, keep the real fault."""
        mqtt_client._update_state(
            {
                "hms": [
                    {"attr": 0x03000300, "code": 0x400C},  # cancel echo — drop
                    {"attr": 0x07FF0200, "code": 0x8011},  # filament runout — keep
                ]
            }
        )
        codes = [e.code for e in mqtt_client.state.hms_errors]
        assert "0x8011" in codes
        assert "0x400c" not in codes
        assert len(mqtt_client.state.hms_errors) == 1

    def test_print_error_path_also_filters_cancel_echo(self, mqtt_client):
        """`print_error` is a second route that appends into state.hms_errors. The
        same user-action codes (e.g. 0500_400E "Printing was cancelled") must be
        filtered there too — otherwise the printer card stays on "1 problem"
        when the firmware reports the cancel via print_error rather than hms[]."""
        mqtt_client._update_state({"print_error": 0x0500_400E})
        assert mqtt_client.state.hms_errors == []

    def test_print_error_path_passes_real_errors_through(self, mqtt_client):
        """Real print_error codes still reach state.hms_errors."""
        mqtt_client._update_state({"print_error": 0x0500_8061})
        assert len(mqtt_client.state.hms_errors) == 1
        assert mqtt_client.state.hms_errors[0].code == "0x8061"

    def test_a_print_error_that_returns_to_zero_is_removed(self, mqtt_client):
        """#3487: the A1 mini sets print_error for the filament-load prompt and
        back to 0 once it is answered on the printer, without an hms[] key.
        The entry stayed until "Clear errors"."""
        mqtt_client._update_state({"print_error": 0x07FF_C010})
        assert [e.full_code for e in mqtt_client.state.hms_errors] == ["07FFC010"]

        mqtt_client._update_state({"print_error": 0})

        assert mqtt_client.state.hms_errors == []

    def test_a_new_print_error_replaces_the_previous_one(self, mqtt_client):
        mqtt_client._update_state({"print_error": 0x07FF_C010})
        mqtt_client._update_state({"print_error": 0x0500_8061})

        assert [e.full_code for e in mqtt_client.state.hms_errors] == ["05008061"]

    def test_the_same_print_error_again_keeps_its_entry(self, mqtt_client):
        """A repeat keeps the entry and the job_id it was frozen with."""
        mqtt_client.state.subtask_id = "job-1"
        mqtt_client._update_state({"print_error": 0x0500_8061})
        entry = mqtt_client.state.hms_errors[0]
        mqtt_client.state.subtask_id = "job-2"

        mqtt_client._update_state({"print_error": 0x0500_8061})

        assert mqtt_client.state.hms_errors == [entry]
        assert entry.job_id == "job-1"

    def test_an_hms_list_without_print_error_keeps_the_print_error_fault(self, mqtt_client):
        """print_error comes only when it changes, so an hms[] update between
        must not drop a fault that is still active."""
        mqtt_client._update_state({"print_error": 0x07FF_C010})

        mqtt_client._update_state({"hms": []})
        assert [e.full_code for e in mqtt_client.state.hms_errors] == ["07FFC010"]

        mqtt_client._update_state({"hms": [{"attr": 0x03000100, "code": 0x00018004}]})
        assert sorted(e.full_code for e in mqtt_client.state.hms_errors) == ["0300010000018004", "07FFC010"]

    def test_an_hms_list_that_now_carries_the_print_error_fault_lists_it_once(self, mqtt_client):
        mqtt_client._update_state({"print_error": 0x0500_8061})

        mqtt_client._update_state({"hms": [{"attr": 0x05000100, "code": 0x00018061}]})

        assert [e.full_code for e in mqtt_client.state.hms_errors] == ["0500010000018061"]
