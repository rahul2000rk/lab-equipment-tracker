#!/bin/sh
python3 -m pip install -q -r requirements.txt && python3 app.py "$@"
