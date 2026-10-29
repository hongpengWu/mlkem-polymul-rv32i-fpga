"""Portable algorithm example: saturated uint8 vector addition; no FPGA emulation claim."""
MEASUREMENT_KIND = "offline-demo"


class Session:
    def describe(self):
        return {"measurement_kind": MEASUREMENT_KIND,
                "operation": "uint8 saturated vector add", "hardware_verified": False}

    def run(self, value, timeout):
        left, right = value["a"], value["b"]
        if len(left) != len(right) or any(type(v) is not int or v < 0 or v > 255 for v in left + right):
            raise ValueError("Require equal-length uint8 vectors")
        return {"output": [min(255, a + b) for a, b in zip(left, right)]}

    def close(self):
        pass


def create(plan, directory):
    return Session()
