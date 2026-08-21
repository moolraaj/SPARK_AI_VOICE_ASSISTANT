from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import (
    VOBIZ_SIP_ADDRESS,
    VOBIZ_SIP_USERNAME,
    VOBIZ_SIP_PASSWORD,
    VOBIZ_PHONE_NUMBER,
)


class VobizSettings(BaseSettings):

    VOBIZ_SIP_ADDRESS: str = VOBIZ_SIP_ADDRESS
    VOBIZ_SIP_USERNAME: str = VOBIZ_SIP_USERNAME
    VOBIZ_SIP_PASSWORD: str = VOBIZ_SIP_PASSWORD
    VOBIZ_PHONE_NUMBER: str = VOBIZ_PHONE_NUMBER

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = VobizSettings()