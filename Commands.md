Install Project in Editable Mode ---> `pip install -e .`
Install With Dev Dependencies ---> `pip install -e .[dev]`
Dependency Management Save Installed Packages ---> 'pip freeze > requirements-dev.txt'
Run All Tests ---> `pytest`
Run All Tests Verbose (Shows detailed test output.) ---> `pytest -v`
Check Code Quality ---> `ruff check .`
Check & Fix Code Quality ---> `ruff check . --fix`
Format Entire Project ---> `black .`
Check Formatting Only ---> `black --check .`

0.1.0  Initial release
0.1.1  Bug fixes
0.2.0  New features
1.0.0  Stable release