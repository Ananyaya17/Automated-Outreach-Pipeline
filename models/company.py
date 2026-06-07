from dataclasses import dataclass


@dataclass
class Company:
    domain: str
    company_name: str

    def __post_init__(self):
        if not self.domain or " " in self.domain or "." not in self.domain:
            raise ValueError("Invalid domain")
        self.domain = self.domain.strip().lower()
