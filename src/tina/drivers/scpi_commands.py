"""
SCPI command constants for VNA control.

This module centralizes all SCPI commands used to control VNAs,
making it easier to maintain and adapt for different instruments.
"""

# Standard SCPI commands (IEEE 488.2)
CMD_IDN = "*IDN?"
CMD_OPC = "*OPC?"
CMD_RESET = "*RST"

# Data format commands
CMD_SET_FORMAT_ASCII = "FORM:DATA ASCII"
CMD_SET_FORMAT_BINARY = "FORM:DATA REAL"

# Sweep control commands
CMD_INIT_CONTINUOUS_ON = "INIT1:CONT ON"
CMD_INIT_CONTINUOUS_OFF = "INIT1:CONT OFF"
CMD_ABORT = "ABOR"
CMD_INIT = "INIT1"

# Sweep type commands
CMD_SET_SWEEP_LINEAR = "SENS1:SWE:TYPE LIN"
CMD_SET_SWEEP_LOG = "SENS1:SWE:TYPE LOG"

# Frequency commands
CMD_GET_FREQ_START = "SENS1:FREQ:STAR?"
CMD_GET_FREQ_STOP = "SENS1:FREQ:STOP?"
CMD_GET_FREQ_DATA = "SENS1:FREQ:DATA?"


def cmd_set_freq_start(freq_hz: float) -> str:
    """Set start frequency."""
    return f"SENS1:FREQ:STAR {freq_hz}"


def cmd_set_freq_stop(freq_hz: float) -> str:
    """Set stop frequency."""
    return f"SENS1:FREQ:STOP {freq_hz}"


# Sweep points commands
CMD_GET_SWEEP_POINTS = "SENS1:SWE:POIN?"


def cmd_set_sweep_points(points: int) -> str:
    """Set number of sweep points."""
    return f"SENS1:SWE:POIN {points}"


# Averaging commands
CMD_GET_AVERAGING_STATE = "SENS1:AVER:STAT?"
CMD_GET_AVERAGING_COUNT = "SENS1:AVER:COUN?"


def cmd_set_averaging_state(enabled: bool) -> str:
    """Set averaging on/off."""
    state = "ON" if enabled else "OFF"
    return f"SENS1:AVER:STAT {state}"


def cmd_set_averaging_count(count: int) -> str:
    """Set averaging count."""
    return f"SENS1:AVER:COUN {count}"


# Parameter configuration commands
def cmd_set_param_count(count: int) -> str:
    """Set number of measurement parameters."""
    return f"CALC1:PAR:COUN {count}"


def cmd_define_param(param_num: int, sparam: str) -> str:
    """Define a measurement parameter (e.g., S11, S21)."""
    return f"CALC1:PAR{param_num}:DEF {sparam}"


def cmd_select_param(param_num: int) -> str:
    """Select a parameter as active."""
    return f"CALC1:PAR{param_num}:SEL"


# Data retrieval commands
CMD_GET_FORMATTED_DATA = "CALC1:DATA:FDAT?"  # Formatted data (mag/phase)
CMD_GET_SDATA = "CALC1:DATA:SDAT?"  # Complex data (real/imag)


# HP E5071B specific commands
class HPE5071B:
    """SCPI commands specific to HP E5071B VNA."""

    # All the above commands apply to E5071B
    # Add E5071B-specific commands here if needed
    pass


# Add other VNA-specific command classes as needed
# class KeysightN9913A:
#     """SCPI commands specific to Keysight N9913A FieldFox."""
#     pass
