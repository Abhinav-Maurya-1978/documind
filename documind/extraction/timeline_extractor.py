import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from dateutil import parser as date_parser

@dataclass
class TimelineAssertion:
    activity_type: str  # 'employment', 'education', 'contract', 'service'
    commitment: str     # 'full-time', 'part-time', 'unspecified'
    role_or_title: Optional[str]
    organization: Optional[str]
    start_year: Optional[int]
    start_month: Optional[int]
    end_year: Optional[int]
    end_month: Optional[int]
    raw_text: str
    evidence_snippet: str

class TimelineExtractor:
    """Extracts chronological periods, commitments, and activities from freeform text."""

    MONTHS = {
        "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
        "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
        "august": 8, "aug": 8, "september": 9, "sep": 9, "october": 10, "oct": 10,
        "november": 11, "nov": 11, "december": 12, "dec": 12
    }

    DEGREE_DURATIONS = {
        "b.tech": 4, "btech": 4, "b.e": 4, "be": 4, "bachelor": 4, "b.s": 4, "bs": 4,
        "mbbs": 5, "b.arch": 5, "m.tech": 2, "mtech": 2, "mba": 2, "m.s": 2, "ms": 2,
        "master": 2, "phd": 4, "ph.d": 4, "diploma": 3
    }

    def extract_timelines(self, text: str) -> List[TimelineAssertion]:
        assertions: List[TimelineAssertion] = []
        sentences = re.split(r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\n)\s*", text)

        for sent in sentences:
            sent_clean = sent.strip()
            if len(sent_clean) < 15:
                continue

            # 1. Detect Employment Timeline: "worked full-time ... from January 2022 to December 2024 as a ..."
            emp_match = re.search(
                r"(?:worked|employed|working|service|served)\s+(?:as\s+)?(full-time|part-time)?\s*(?:at\s+[^\n\.,]+)?\s*from\s+([A-Za-z]+)\s+(\d{4})\s+to\s+([A-Za-z]+)\s+(\d{4})(?:\s+as\s+(?:a\s+)?([A-Za-z0-9\s\-]+))?",
                sent_clean,
                re.IGNORECASE
            )
            if emp_match:
                commit = emp_match.group(1).lower() if emp_match.group(1) else ("full-time" if "full-time" in sent_clean.lower() else "unspecified")
                s_month_str = emp_match.group(2).lower()
                s_year = int(emp_match.group(3))
                e_month_str = emp_match.group(4).lower()
                e_year = int(emp_match.group(5))
                role = emp_match.group(6).strip() if emp_match.group(6) else None

                s_month = self.MONTHS.get(s_month_str, 1)
                e_month = self.MONTHS.get(e_month_str, 12)

                assertions.append(
                    TimelineAssertion(
                        activity_type="employment",
                        commitment=commit,
                        role_or_title=role,
                        organization=None,
                        start_year=s_year,
                        start_month=s_month,
                        end_year=e_year,
                        end_month=e_month,
                        raw_text=f"Employed ({commit}) from {s_month_str.title()} {s_year} to {e_month_str.title()} {e_year}" + (f" as {role}" if role else ""),
                        evidence_snippet=sent_clean,
                    )
                )

            # 2. Detect Education Timeline: "completed my B.Tech in Computer Science and graduated in June 2025 ... as a regular full-time student"
            edu_match = re.search(
                r"(?:graduated|completed|degree|passed|studies|studying)\s+(?:in|from|at)?\s*([A-Za-z0-9\s\.\-]+?)?\s*graduated\s+in\s+([A-Za-z]+)\s+(\d{4})|graduated\s+in\s+([A-Za-z]+)\s+(\d{4})",
                sent_clean,
                re.IGNORECASE
            )
            if "graduat" in sent_clean.lower() or "b.tech" in sent_clean.lower() or "degree" in sent_clean.lower() or "student" in sent_clean.lower():
                grad_match = re.search(r"graduated\s+in\s+([A-Za-z]+)\s+(\d{4})", sent_clean, re.IGNORECASE)
                if grad_match:
                    e_month_str = grad_match.group(1).lower()
                    e_year = int(grad_match.group(2))
                    e_month = self.MONTHS.get(e_month_str, 6)

                    # Determine degree duration
                    duration_years = 4  # Default bachelor
                    degree_name = "Degree"
                    lower_s = sent_clean.lower()
                    for deg, dur in self.DEGREE_DURATIONS.items():
                        if deg in lower_s:
                            duration_years = dur
                            degree_name = deg.upper()
                            break

                    commit = "full-time" if "full-time" in lower_s or "regular" in lower_s else "unspecified"
                    # In India/US, an undergraduate graduating in June 2025 started in August (2025 - duration)
                    s_year = e_year - duration_years
                    s_month = 8  # August start of academic year

                    assertions.append(
                        TimelineAssertion(
                            activity_type="education",
                            commitment=commit,
                            role_or_title=f"{degree_name} Student",
                            organization=None,
                            start_year=s_year,
                            start_month=s_month,
                            end_year=e_year,
                            end_month=e_month,
                            raw_text=f"Regular Student ({commit}) {degree_name} enrolled {s_year} to graduation in {e_month_str.title()} {e_year}",
                            evidence_snippet=sent_clean,
                        )
                    )

            # 3. Generic Date Interval: "between [Year] and [Year]" or "[Month Year] - [Month Year]"
            gen_match = re.search(
                r"(?:between|from|period|duration)\s*[:=\-]?\s*([A-Za-z]+)?\s*(\d{4})\s*(?:to|-|and)\s*([A-Za-z]+)?\s*(\d{4})",
                sent_clean,
                re.IGNORECASE
            )
            if gen_match and not emp_match:
                s_y = int(gen_match.group(2))
                e_y = int(gen_match.group(4))
                commit = "full-time" if "full-time" in sent_clean.lower() else "unspecified"
                assertions.append(
                    TimelineAssertion(
                        activity_type="general_timeline",
                        commitment=commit,
                        role_or_title=None,
                        organization=None,
                        start_year=s_y,
                        start_month=1,
                        end_year=e_y,
                        end_month=12,
                        raw_text=f"Timeline interval {s_y} to {e_y}",
                        evidence_snippet=sent_clean,
                    )
                )

        return assertions
