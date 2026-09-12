import unittest
from unittest.mock import Mock
from tools.audio_backend import check_selected, filter_devices


class AudioBackendTests(unittest.TestCase):
    def setUp(self):
        self.apis = [{"name": "MME"}, {"name": "WASAPI"}]
        self.devices = [dict(name="USB", hostapi=api, max_input_channels=2,
                             max_output_channels=2, default_samplerate=48000) for api in (0, 1)]

    def test_exclusion_preserves_indices_other_apis_and_other_direction(self):
        result = filter_devices(self.devices, self.apis, [{"name": "USB", "hostapi": "MME", "direction": "input"}])
        self.assertEqual(result[0]["max_input_channels"], 0)
        self.assertEqual(result[0]["max_output_channels"], 2)
        self.assertEqual(result[1]["max_input_channels"], 2)
        self.assertEqual(result[1]["index"], 1)
        self.assertEqual(self.devices[0]["max_input_channels"], 2)

    def test_only_failed_selected_endpoint_is_ignored(self):
        sd = Mock()
        sd.query_devices.return_value = self.devices
        sd.query_hostapis.return_value = self.apis
        sd.RawInputStream.side_effect = RuntimeError("unavailable")
        failed = check_selected(sd, {"sg_hostapi": "MME", "sg_input_device": "USB", "sg_output_device": "USB"})
        self.assertEqual(failed, [{"name": "USB", "hostapi": "MME", "direction": "input"}])
        sd.RawOutputStream.return_value.close.assert_called_once()

    def test_missing_endpoint_is_reported_and_empty_selection_is_not(self):
        sd = Mock()
        sd.query_devices.return_value = self.devices
        sd.query_hostapis.return_value = self.apis
        self.assertEqual(check_selected(sd, {}), [])
        failed = check_selected(sd, {"sg_hostapi": "MME", "sg_input_device": "disconnected"})
        self.assertEqual(failed[0]["name"], "disconnected")
        sd.RawInputStream.assert_not_called()


if __name__ == "__main__":
    unittest.main()
