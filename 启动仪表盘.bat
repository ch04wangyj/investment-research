@echo off
cd /d "E:\ClaudeCode\workspace\investment-research"
call C:\Users\wang_2004\anaconda3\Scripts\activate.bat invest
streamlit run src\dashboard\app.py
pause
