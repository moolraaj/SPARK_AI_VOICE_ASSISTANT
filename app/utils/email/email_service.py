import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.core.config import (SMTP_EMAIL,SMTP_PASSWORD,SMTP_PORT,SMTP_HOST)

class EmailService:

    @staticmethod
    def send_email(
        receiver_email: str,
        subject: str,
        body: str
    ):

        message = MIMEMultipart()

        message["From"] = SMTP_EMAIL

        message["To"] = receiver_email

        message["Subject"] = subject

        message.attach(
            MIMEText(
                body,
                "html"
            )
        )

        with smtplib.SMTP(
            SMTP_HOST,
            SMTP_PORT
        ) as server:

            server.starttls()

            server.login(
                SMTP_EMAIL,
                SMTP_PASSWORD
            )

            server.send_message(message)