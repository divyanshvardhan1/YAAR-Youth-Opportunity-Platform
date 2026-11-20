# Deploy Y.A.A.R. on PythonAnywhere

> These instructions are for an **academic demo**. Do not publish genuine user data. **This repository's SQLite database is intentionally excluded.**

## Option A: Fresh upload from your computer

1. Create a PythonAnywhere account and open **Files**.
2. Upload a ZIP containing the source files, then open **Consoles → Bash**.
3. Extract the ZIP and use `ls` to check the actual directory name. **Use the path that really exists**; do not assume the ZIP filename and extracted folder have the same spelling.
4. Go to **Web → Add a new web app → Manual configuration → Python 3.11** (or another available Python 3.8+ version).
5. Under **Web → Code**, click the **WSGI configuration file**.
6. Replace the sample WSGI content with the following, adjusting the username and source directory:

```python
import sys

path = '/home/YOUR_PYTHONANYWHERE_USERNAME/YOUR_EXTRACTED_FOLDER'
if path not in sys.path:
    sys.path.insert(0, path)

from wsgi import application
```

7. Save, return to **Web**, click **Reload**, and visit `https://YOUR_PYTHONANYWHERE_USERNAME.pythonanywhere.com`.
8. If you see an error, inspect the **Error log** under the Web tab, and confirm `app.py`, `wsgi.py` and `static/style.css` exist under the chosen source directory.

## Option B: Updating an existing deployment

Your GitHub repository and PythonAnywhere files do **not** sync by default. Committing a change to GitHub alone will **not** update the live website. To update, upload/retrieve the changed source files on PythonAnywhere, then **Reload** in the Web tab.

Do **not** overwrite your live SQLite file (`yaar.db`) without a backup; it contains account and application data. For a public deployment, remove shared demo logins, verify the application security, and consider a production data storage/backup plan.

## Notes

- `START-YAAR.bat` is a Windows local launcher, not a cloud start command.
- `wsgi.py` initializes a SQLite database on first import.
- The project uses the Python standard library; no extra `pip install` is needed for the current implementation.
- PythonAnywhere plan limits, renewal and availability can change; review the platform dashboard for current terms.
