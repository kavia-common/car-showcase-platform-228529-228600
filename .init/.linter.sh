#!/bin/bash
cd /home/kavia/workspace/code-generation/car-showcase-platform-228529-228600/car_brochure_backend
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

