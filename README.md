~Setup:

cd backend

python -m venv .venv

.venv\Scripts\activate

pip install -r requirements.txt

python -m app.ingestion

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

--------------------------------------------------------------------

~Sample prompts:

„I want to read a book based on a war story”

„I want a book with a science fiction story behind it”

„What is 1984?”
