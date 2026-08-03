import sys
sys.path.append(".")
from guardrails.check_intent_parser import check

good = {"source_subnet": "10.0.5.0/24", "dest_subnet": "10.0.10.15/32",
        "dest_port": 443, "protocol": "tcp", "confidence": 0.95}
print("Валиден пример:", check(good))

bad = {"source_subnet": "not-an-ip", "dest_subnet": "10.0.10.15/32",
       "dest_port": 70000, "protocol": "tcp", "confidence": 0.95}
print("Невалиден пример:", check(bad))