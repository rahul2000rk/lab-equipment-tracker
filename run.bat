@echo off
py -m pip install -q -r requirements.txt
py app.py %*
