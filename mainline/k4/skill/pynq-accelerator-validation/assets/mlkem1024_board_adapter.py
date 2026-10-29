"""Live adapter to the existing project driver. No algorithm logic in the runner."""
import hashlib
import importlib.util
from pathlib import Path
MEASUREMENT_KIND = "board-live"


class Session:
    def __init__(self, driver, provenance):
        self.driver, self.provenance = driver, provenance

    def describe(self):
        return dict(measurement_kind=MEASUREMENT_KIND, firmware_mode=self.driver.firmware_mode,
                    driver_sha256=self.provenance, bundle=self.driver.artifacts)

    def run(self, value, timeout):
        record = self.driver.run_case(value["case_index"], timeout=timeout)
        return {"output": {"hex": record["output_hex"], "return_code": record["return_code"]},
                "device_cycles": record["raw_cycles"], "frequency_hz": record["frequency_hz"],
                "cycle_scope": "firmware API rdcycle region, before empty-call subtraction",
                "detail": record}

    def close(self):
        # Stop CPU even when comparison or polling failed.
        self.driver.reset()


def create(plan, directory):
    config = plan["adapter_config"]
    bundle = (directory / config["bundle_directory"]).resolve()
    driver_path = bundle / "mlkem1024.py"
    spec = importlib.util.spec_from_file_location("validation_mlkem1024", str(driver_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    driver = module.MLKEM1024.load(bundle / "release_manifest.json")
    try:
        if driver.paired_firmware:
            driver.select_firmware(config["firmware_mode"])
        elif config.get("firmware_mode", "accelerated") != "accelerated":
            raise ValueError("This bundle does not support firmware switching")
        return Session(driver, hashlib.sha256(driver_path.read_bytes()).hexdigest())
    except Exception:
        driver.reset()
        raise
