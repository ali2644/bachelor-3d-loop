import requests


class QualityStationClient:
    def __init__(self, base_url: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def measure(self) -> dict[str, float]:
        response = requests.post(
            f"{self.base_url}/measurements",
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        return data["results"]