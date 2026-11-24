# AI Data Quality Assistant

A small Streamlit app that checks CSV and Excel files for possible data-quality issues.

## Files
- `app.py` — web interface
- `data_quality_checker.py` — analysis checks
- `requirements.txt` — Python dependencies

## Run locally
```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Deploy
1. Create a GitHub repository and upload these three files.
2. In Streamlit Community Cloud, create an app from that repository.
3. Set the main file path to `app.py`.
4. Deploy.

## Important notes
- The uploaded source data is not automatically corrected.
- Flags are suggestions for review, not proof of errors.
- The row number shown assumes the first spreadsheet row contains column headers.
- The app currently reports issues; AI-generated interpretation and report writing can be added as a later stage.
