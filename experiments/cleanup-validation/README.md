# Cleanup validation

Fresh results from the cleanup branch; historical experiment directories were not
changed. pytest.log covers all 176 active tests, including the 13 real Java/RMC/g++
tests. lint.log records strict mypy and flake8. Gate and handbook smoke artifacts
are actual outputs; absolute temporary paths identify the original run and may no
longer exist. No binaries, C++ builds, or statespaces are retained here.
The satisfied gate CLI run intentionally disabled optional diagnostics; real
mutation/vacuity checks are covered separately in pytest.
