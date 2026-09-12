from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ---------- Auth ----------

class LoginRequest(BaseModel):
    identifier: str = Field(..., description="Email or phone number")
    password: str


class RegisterRequest(BaseModel):
    fullName: str
    phoneNumber: str
    email: EmailStr
    homeAddress: str
    idNumber: str
    thriftPlan: str
    password: str
    confirmPassword: str


class ForgotPasswordRequest(BaseModel):
    identifier: str


class VerifyOtpRequest(BaseModel):
    identifier: str
    otp: str


class ResetPasswordRequest(BaseModel):
    identifier: str
    otp: str
    newPassword: str


class ChangePasswordRequest(BaseModel):
    currentPassword: str
    newPassword: str


class TokenResponse(BaseModel):
    accessToken: str
    tokenType: str = "bearer"
    user: "UserOut"


# ---------- Users ----------

class UserOut(BaseModel):
    id: int
    fullName: str
    phoneNumber: str
    email: str
    homeAddress: str
    idNumber: str
    thriftPlan: str
    role: str
    status: str
    savingsBalance: float
    targetAmount: float
    createdAt: int

    class Config:
        from_attributes = True


class UserCreateByAdmin(BaseModel):
    fullName: str
    phoneNumber: str
    email: EmailStr
    homeAddress: str
    idNumber: str
    thriftPlan: str
    targetAmount: float = 100000.0
    initialBalance: float = 0.0


class UserUpdate(BaseModel):
    fullName: Optional[str] = None
    phoneNumber: Optional[str] = None
    homeAddress: Optional[str] = None
    thriftPlan: Optional[str] = None
    targetAmount: Optional[float] = None


class MessageRequest(BaseModel):
    title: str
    message: str


class RejectRequest(BaseModel):
    reason: str = "KYC documents incomplete"


# ---------- Transactions ----------

class ContributionRequest(BaseModel):
    amount: float
    plan: str
    paymentMethod: str
    channelReference: str = ""
    notes: str = ""


class FailedContributionRequest(BaseModel):
    amount: float
    plan: str
    paymentMethod: str
    channelReference: str = ""
    failureReason: str = "Payment declined by issuing bank"


class TransactionOut(BaseModel):
    id: int
    reference: str
    userId: int
    customerName: str
    amount: float
    plan: str
    paymentMethod: str
    status: str
    channelReference: Optional[str] = None
    timestamp: int
    notes: str

    class Config:
        from_attributes = True


# ---------- Notifications ----------

class NotificationOut(BaseModel):
    id: int
    recipientRole: str
    userId: Optional[int] = None
    title: str
    message: str
    isRead: bool
    timestamp: int

    class Config:
        from_attributes = True


# ---------- Audit Logs ----------

class AuditLogOut(BaseModel):
    id: int
    actorName: str
    actorRole: str
    action: str
    details: str
    timestamp: int

    class Config:
        from_attributes = True


# ---------- Reports ----------

class ReportSummary(BaseModel):
    range: str
    startTimestamp: int
    endTimestamp: int
    totalCollected: float
    numberOfTransactions: int
    activeSavers: int
    defaulters: int


# ---------- Payments ----------

class PaymentInitRequest(BaseModel):
    gateway: str = Field(..., description="'Paystack' or 'Flutterwave'")
    amount: float
    plan: str


class PaymentInitResponse(BaseModel):
    isSuccess: bool
    reference: str
    accessCode: str
    authorizationUrl: str
    message: str


class PaymentVerifyRequest(BaseModel):
    gateway: str = Field(..., description="'Paystack' or 'Flutterwave'")
    amount: float
    plan: str
    paymentMethod: str
    cardNumber: str = ""


class PaymentVerifyResponse(BaseModel):
    isSuccess: bool
    reference: str
    amount: float
    gatewayResponse: str
    paymentMethod: str
    channelReference: str
    transaction: Optional[TransactionOut] = None


TokenResponse.model_rebuild()
