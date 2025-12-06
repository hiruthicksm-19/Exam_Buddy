@echo off
echo Installing required packages...
pip install -r requirements.txt

echo.
echo Starting Exam Buddy...
streamlit run app.py
