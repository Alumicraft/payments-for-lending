"""Pure business rules shared by DCR Lending overrides."""


def has_material_outstanding_principal(
    loan_amount,
    total_principal_paid,
    current_principal_paid=0,
    write_off_amount=0,
    precision=2,
):
    """Return whether principal remains above the configured write-off limit."""
    remaining = round(
        float(loan_amount or 0)
        - float(total_principal_paid or 0)
        - float(current_principal_paid or 0),
        precision,
    )
    return remaining > float(write_off_amount or 0)
