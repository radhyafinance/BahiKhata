## Auth Testing Playbook

Step 1: MongoDB Verification
mongosh
use bahikhata_db
db.users.find({role: "admin"}).pretty()
db.users.findOne({role: "admin"}, {password_hash: 1})
Verify: bcrypt hash starts with $2b$, indexes exist on users.email (unique)

Step 2: API Testing
curl -c cookies.txt -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@bahikhata.com","password":"Admin@123"}'
cat cookies.txt
curl -b cookies.txt http://localhost:8001/api/auth/me

Login should return the user object and set access_token cookie. The /me call should return the same user using those cookies.
