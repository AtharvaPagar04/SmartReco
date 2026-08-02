from pydantic import BaseModel, EmailStr, Field, field_validator


class RegistrationForm(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    password_confirm: str = Field(min_length=8, max_length=128)

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Name is too short")
        return value

    def matching_passwords(self) -> bool:
        return self.password == self.password_confirm


class LoginForm(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
