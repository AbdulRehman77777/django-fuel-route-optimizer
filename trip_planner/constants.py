from decimal import Decimal

MAX_RANGE_MILES = Decimal("500")
MPG = Decimal("10")
TANK_CAPACITY_GALLONS = MAX_RANGE_MILES / MPG
METERS_PER_MILE = Decimal("1609.344")
GEOCODED_STATION_STATUSES = ("census_matched", "ors_matched", "imported_coordinates")
US_STATE_CODES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT",
    "VT", "VA", "WA", "WV", "WI", "WY", "DC",
})
