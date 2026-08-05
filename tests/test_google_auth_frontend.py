from pathlib import Path


def test_google_auth_controls_are_present_without_nested_forms():
    root = Path(__file__).parents[1]
    login = (root / "app/templates/auth/login.html").read_text()
    register = (root / "app/templates/auth/register.html").read_text()
    account = (root / "app/templates/account/index.html").read_text()

    assert "Continue with Google" in login
    assert "Continue with Google" in register
    assert "google_auth_enabled" in login and "google_auth_enabled" in register
    assert login.count("<form") == 1
    assert register.count("<form") == 1
    assert "Sign-in methods" in account
    assert "provider_subject" not in account
