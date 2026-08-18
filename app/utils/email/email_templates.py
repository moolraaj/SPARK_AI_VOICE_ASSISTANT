
def forgot_password_template(
    name: str,
    otp: str,
    time:int
):

    return f"""
    <h2>Hello {name},</h2>

    <p>Your password reset OTP is:</p>

    <h1>{otp}</h1>

    <p>This OTP will expire in {time} minutes.</p>

    <p>If you didn't request this, please ignore this email.</p>
    """