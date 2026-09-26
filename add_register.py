import re

# 1. Add create to SqlUserRepository
with open("backend/src/tram/infrastructure/auth.py", "r", encoding="utf-8") as f:
    content = f.read()

create_method = '''
    def create(self, user_id: str, username: str, password_hash: str, role: str) -> None:
        import sqlalchemy.exc
        with self.session_factory() as session:
            try:
                session.add(UserRow(
                    id=user_id,
                    username=username,
                    password_hash=password_hash,
                    role=role,
                    is_active=True
                ))
                session.commit()
            except sqlalchemy.exc.IntegrityError:
                raise ValueError("User already exists")
'''

content = content.replace('    def get_by_id(self, user_id: str) -> Document | None:', create_method + '\n    def get_by_id(self, user_id: str) -> Document | None:')
with open("backend/src/tram/infrastructure/auth.py", "w", encoding="utf-8") as f:
    f.write(content)

# 2. Add register to AuthService
with open("backend/src/tram/application/auth.py", "r", encoding="utf-8") as f:
    content = f.read()

register_method = '''
    def register(self, username: str, password: str) -> dict:
        import uuid
        user_id = str(uuid.uuid4())
        hashed = self.hasher.hash(password)
        try:
            self.users.create(user_id, username, hashed, "operator")
        except ValueError:
            raise ApplicationError("VALIDATION_ERROR", "Username already exists")
        return {"id": user_id}
'''

content = content.replace('    def login(', register_method + '\n    def login(')
with open("backend/src/tram/application/auth.py", "w", encoding="utf-8") as f:
    f.write(content)

# 3. Add authRegister to auth_bindings
with open("backend/src/tram/api/extensions.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace('    commands = {\n        "authLogin":', '    commands = {\n        "authRegister": lambda p, c, r: service.register(c["username"], c["password"]),\n        "authLogin":')
with open("backend/src/tram/api/extensions.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Added register methods!")
