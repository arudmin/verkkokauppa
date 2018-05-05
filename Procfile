bot: python3 bot/app.py

# web: gunicorn --chdir api test:app --max-requests 1200 --timeout 30
# web: gunicorn verk run:app
web: gunicorn --chdir app run:app
