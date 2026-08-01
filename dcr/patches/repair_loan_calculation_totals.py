from dcr.setup import ensure_lending_calculation_values


def execute():
    """Repair submitted Loan totals after the qualifying-amount alias fix."""
    ensure_lending_calculation_values()
