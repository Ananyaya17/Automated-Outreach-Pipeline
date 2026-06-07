from dataclasses import dataclass
from typing import Optional


@dataclass
class Contact:
    full_name: str
    title: str
    linkedin_url: Optional[str]
    email: Optional[str]
    company_domain: str

    def __post_init__(self):
        self.company_domain = self.company_domain.strip().lower()

    @property
    def first_name(self) -> str:
        return self.full_name.split()[0] if self.full_name else ""
