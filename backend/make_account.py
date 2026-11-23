import sys

from sqlalchemy import select
from user.app.database import SessionLocal, init_db
from user.app.models.user import User
from user.app.services.auth import POSITION_ROLES, hash_password

if len(sys.argv) < 4:
    sys.exit(__doc__)

unit_code, username, password = sys.argv[1:4]
position = sys.argv[4] if len(sys.argv) > 4 else "동대장"
if position not in POSITION_ROLES:
    sys.exit("구분은 동대장 / 상근예비역 / 감사실 중 하나여야 합니다.")


init_db()  # unit_code, position 컬럼이 없으면 추가
db = SessionLocal()
user = db.scalar(select(User).where(User.username == username))

if user is None:
    user = User(username=username, password_hash="")
    db.add(user)

user.unit_code = unit_code
user.position = position
user.role = POSITION_ROLES[position]
user.password_hash = hash_password(password)
user.is_active = True

db.commit()

print(f"완료: [{unit_code}] {username} · {position}")