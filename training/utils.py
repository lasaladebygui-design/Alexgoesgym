from decimal import Decimal

KG_PER_LB = Decimal("0.45359237")


def to_kg(value, unit):
    """value en la unidad que sea -> kg (unidad canónica de almacenamiento).
    Todo el peso se guarda siempre en kg internamente para que comparar
    PRs/volumen entre entradas en kg y en lb no requiera conversión al
    vuelo ni arrastre errores de redondeo acumulados."""
    if value is None:
        return None
    value = Decimal(value)
    return value if unit == "kg" else (value * KG_PER_LB)


def from_kg(value_kg, unit):
    """kg -> la unidad que se quiera mostrar."""
    if value_kg is None:
        return None
    if unit == "kg":
        return value_kg
    return value_kg / KG_PER_LB


def estimated_1rm(weight_kg, reps):
    """Fórmula de Epley: 1RM ≈ peso × (1 + reps/30). Es una estimación --
    a partir de ~12 reps pierde bastante fiabilidad, pero es el estándar
    más usado en trackers de fuerza y vale para ver tendencia, no para
    prescribir con precisión quirúrgica."""
    if weight_kg is None or not reps:
        return None
    if reps == 1:
        return weight_kg
    return weight_kg * (Decimal("1") + Decimal(reps) / Decimal("30"))
