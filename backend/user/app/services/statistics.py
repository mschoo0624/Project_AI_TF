"""Statistics services."""
import numpy as np
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from user.app.models.assignment import Assignment
from user.app.models.person import Person
from user.app.models.squad import Squad

