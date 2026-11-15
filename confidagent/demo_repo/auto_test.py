# safety_test.py

def get_value():
    return 100

# demo_repo\auth.py

def get_safety_test_value():
    from safety_test import get_value
    return get_value()

# demo_repo\constants.py

class SafetyTestConstants:
    def __init__(self):
        self.SAFETY_TEST_VALUE = get_safety_test_value()

    def get_safety_test_value(self):
        return self.SAFETY_TEST_VALUE
