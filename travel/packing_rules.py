"""
Smart Packing Rules Engine
Generates packing lists based on weather forecasts and trip duration.
Uses a rules-based system — no external AI APIs needed.
"""


# =====================================================
# BASE ESSENTIALS — always packed regardless of weather
# =====================================================
BASE_ESSENTIALS = [
    {"name": "Passport / ID", "category": "Documents", "emoji": "🪪", "reason": "Essential travel document", "is_weather_based": False},
    {"name": "Travel Insurance Docs", "category": "Documents", "emoji": "📋", "reason": "Emergency preparedness", "is_weather_based": False},
    {"name": "Boarding Pass / Tickets", "category": "Documents", "emoji": "🎫", "reason": "Required for travel", "is_weather_based": False},
    {"name": "Phone Charger", "category": "Electronics", "emoji": "🔌", "reason": "Keep devices powered", "is_weather_based": False},
    {"name": "Power Bank", "category": "Electronics", "emoji": "🔋", "reason": "Backup battery on-the-go", "is_weather_based": False},
    {"name": "Earphones / Headphones", "category": "Electronics", "emoji": "🎧", "reason": "Entertainment during travel", "is_weather_based": False},
    {"name": "Toothbrush & Toothpaste", "category": "Toiletries", "emoji": "🪥", "reason": "Daily hygiene", "is_weather_based": False},
    {"name": "Deodorant", "category": "Toiletries", "emoji": "🧴", "reason": "Stay fresh", "is_weather_based": False},
    {"name": "Shampoo (travel-size)", "category": "Toiletries", "emoji": "🧴", "reason": "Hair care", "is_weather_based": False},
    {"name": "Medications", "category": "Essentials", "emoji": "💊", "reason": "Health essentials", "is_weather_based": False},
    {"name": "First Aid Kit", "category": "Essentials", "emoji": "🩹", "reason": "Minor injuries", "is_weather_based": False},
    {"name": "Reusable Water Bottle", "category": "Essentials", "emoji": "🥤", "reason": "Stay hydrated", "is_weather_based": False},
    {"name": "Wallet / Cash / Cards", "category": "Essentials", "emoji": "💳", "reason": "Payments", "is_weather_based": False},
    {"name": "Underwear", "category": "Clothing", "emoji": "👔", "reason": "Daily wear", "is_weather_based": False},
    {"name": "Socks", "category": "Clothing", "emoji": "🧦", "reason": "Daily wear", "is_weather_based": False},
    {"name": "Comfortable Walking Shoes", "category": "Clothing", "emoji": "👟", "reason": "Sightseeing comfort", "is_weather_based": False},
    {"name": "Sleepwear", "category": "Clothing", "emoji": "👕", "reason": "Comfortable rest", "is_weather_based": False},
]


# =====================================================
# WEATHER-BASED RULES
# =====================================================
def get_weather_items(weather_summary):
    """
    Analyze weather summary and return weather-specific packing items.
    
    weather_summary expected format:
    {
        "avg_temp": float (°C),
        "min_temp": float,
        "max_temp": float,
        "rain_chance": float (0-100),
        "snow_chance": float (0-100),
        "avg_humidity": float (0-100),
        "max_wind_speed": float (km/h),
        "conditions": list of str (e.g., ["Rain", "Clouds", "Clear"])
    }
    """
    items = []
    
    avg_temp = weather_summary.get("avg_temp", 25)
    min_temp = weather_summary.get("min_temp", 20)
    max_temp = weather_summary.get("max_temp", 30)
    rain_chance = weather_summary.get("rain_chance", 0)
    snow_chance = weather_summary.get("snow_chance", 0)
    humidity = weather_summary.get("avg_humidity", 50)
    wind_speed = weather_summary.get("max_wind_speed", 0)
    
    # --- RAIN RULES ---
    if rain_chance > 30:
        items.extend([
            {"name": "Umbrella", "category": "Weather Gear", "emoji": "☂️", "reason": f"Rain forecast ({rain_chance:.0f}% chance)", "is_weather_based": True},
            {"name": "Rain Jacket / Poncho", "category": "Weather Gear", "emoji": "🧥", "reason": f"Rain expected during trip", "is_weather_based": True},
            {"name": "Waterproof Bag Cover", "category": "Weather Gear", "emoji": "🎒", "reason": "Protect belongings from rain", "is_weather_based": True},
        ])
    if rain_chance > 60:
        items.append(
            {"name": "Waterproof Shoes / Boots", "category": "Clothing", "emoji": "🥾", "reason": f"Heavy rain likely ({rain_chance:.0f}%)", "is_weather_based": True}
        )
    
    # --- COLD RULES ---
    if min_temp < 15:
        items.extend([
            {"name": "Warm Jacket / Coat", "category": "Clothing", "emoji": "🧥", "reason": f"Cold weather (low of {min_temp:.0f}°C)", "is_weather_based": True},
            {"name": "Thermal Inner Wear", "category": "Clothing", "emoji": "🧣", "reason": f"Temperatures drop to {min_temp:.0f}°C", "is_weather_based": True},
        ])
    if min_temp < 10:
        items.extend([
            {"name": "Gloves", "category": "Weather Gear", "emoji": "🧤", "reason": f"Very cold ({min_temp:.0f}°C expected)", "is_weather_based": True},
            {"name": "Scarf / Muffler", "category": "Weather Gear", "emoji": "🧣", "reason": f"Wind chill protection", "is_weather_based": True},
            {"name": "Warm Beanie / Hat", "category": "Weather Gear", "emoji": "🧢", "reason": f"Keep head warm in {min_temp:.0f}°C", "is_weather_based": True},
        ])
    if min_temp < 5:
        items.append(
            {"name": "Hand Warmers", "category": "Weather Gear", "emoji": "🔥", "reason": f"Near-freezing temps ({min_temp:.0f}°C)", "is_weather_based": True}
        )
    
    # --- HOT RULES ---
    if max_temp > 30:
        items.extend([
            {"name": "Sunscreen (SPF 50+)", "category": "Toiletries", "emoji": "🧴", "reason": f"Hot weather ({max_temp:.0f}°C expected)", "is_weather_based": True},
            {"name": "Sunglasses", "category": "Weather Gear", "emoji": "🕶️", "reason": f"UV protection in {max_temp:.0f}°C heat", "is_weather_based": True},
            {"name": "Sun Hat / Cap", "category": "Clothing", "emoji": "🧢", "reason": f"Sun protection needed", "is_weather_based": True},
            {"name": "Light Cotton Clothes", "category": "Clothing", "emoji": "👕", "reason": f"Breathable fabric for {max_temp:.0f}°C", "is_weather_based": True},
        ])
    if max_temp > 35:
        items.extend([
            {"name": "Cooling Towel", "category": "Essentials", "emoji": "🧊", "reason": f"Extreme heat ({max_temp:.0f}°C)", "is_weather_based": True},
            {"name": "Electrolyte Packets", "category": "Essentials", "emoji": "💧", "reason": f"Prevent dehydration in {max_temp:.0f}°C", "is_weather_based": True},
        ])
    
    # --- SNOW RULES ---
    if snow_chance > 20:
        items.extend([
            {"name": "Snow Boots", "category": "Clothing", "emoji": "🥾", "reason": f"Snow forecast ({snow_chance:.0f}% chance)", "is_weather_based": True},
            {"name": "Thermal Layers", "category": "Clothing", "emoji": "🧥", "reason": "Layered warmth for snow", "is_weather_based": True},
            {"name": "Waterproof Pants", "category": "Clothing", "emoji": "👖", "reason": "Stay dry in snow", "is_weather_based": True},
        ])
    
    # --- HUMIDITY RULES ---
    if humidity > 80:
        items.extend([
            {"name": "Moisture-Wicking Clothes", "category": "Clothing", "emoji": "💨", "reason": f"High humidity ({humidity:.0f}%)", "is_weather_based": True},
            {"name": "Extra Towel", "category": "Essentials", "emoji": "🏖️", "reason": f"Humidity at {humidity:.0f}%", "is_weather_based": True},
            {"name": "Anti-Chafing Cream", "category": "Toiletries", "emoji": "🧴", "reason": f"Humid conditions", "is_weather_based": True},
        ])
    
    # --- WIND RULES ---
    if wind_speed > 30:
        items.extend([
            {"name": "Windbreaker Jacket", "category": "Weather Gear", "emoji": "🌬️", "reason": f"Strong winds ({wind_speed:.0f} km/h)", "is_weather_based": True},
            {"name": "Secured Hat (with strap)", "category": "Weather Gear", "emoji": "🧢", "reason": f"Windy conditions", "is_weather_based": True},
        ])
    
    # --- MILD / PLEASANT WEATHER ---
    if 20 <= avg_temp <= 28 and rain_chance < 30 and humidity < 70:
        items.extend([
            {"name": "Light Jacket (evenings)", "category": "Clothing", "emoji": "🧥", "reason": f"Pleasant weather (~{avg_temp:.0f}°C), cool evenings", "is_weather_based": True},
            {"name": "Casual Wear", "category": "Clothing", "emoji": "👕", "reason": f"Great weather for sightseeing", "is_weather_based": True},
        ])
    
    return items


# =====================================================
# DURATION-BASED RULES
# =====================================================
def get_duration_items(num_days):
    """Add items based on trip length."""
    items = []
    
    if num_days >= 3:
        items.append(
            {"name": "Laundry Bag", "category": "Essentials", "emoji": "👜", "reason": f"{num_days}-day trip — keep dirty clothes separate", "is_weather_based": False}
        )
    
    if num_days >= 5:
        items.extend([
            {"name": "Travel Detergent", "category": "Essentials", "emoji": "🧼", "reason": f"Wash clothes during {num_days}-day trip", "is_weather_based": False},
            {"name": "Extra Pair of Shoes", "category": "Clothing", "emoji": "👞", "reason": f"Longer trip — shoes get worn", "is_weather_based": False},
        ])
    
    if num_days >= 7:
        items.extend([
            {"name": "Travel Adapter / Multi-plug", "category": "Electronics", "emoji": "🔌", "reason": "Extended trip convenience", "is_weather_based": False},
            {"name": "Portable Clothesline", "category": "Essentials", "emoji": "🧵", "reason": f"Dry clothes during {num_days}-day trip", "is_weather_based": False},
        ])
    
    return items


# =====================================================
# MAIN GENERATOR
# =====================================================
CATEGORY_ORDER = ["Essentials", "Documents", "Clothing", "Weather Gear", "Toiletries", "Electronics"]

def generate_packing_list(weather_summary, num_days):
    """
    Master function: generates a complete, categorized packing list.
    
    Returns:
    {
        "items": [{ name, category, emoji, reason, is_weather_based, checked }],
        "categories": { "Essentials": [...], "Clothing": [...], ... },
        "stats": { "total": int, "weather_based": int, "categories": int }
    }
    """
    all_items = []
    
    # 1. Base essentials
    all_items.extend(BASE_ESSENTIALS)
    
    # 2. Weather-based items
    weather_items = get_weather_items(weather_summary)
    all_items.extend(weather_items)
    
    # 3. Duration-based items
    duration_items = get_duration_items(num_days)
    all_items.extend(duration_items)
    
    # Add checked=False to all items
    for item in all_items:
        item["checked"] = False
    
    # Deduplicate by name
    seen_names = set()
    unique_items = []
    for item in all_items:
        if item["name"] not in seen_names:
            seen_names.add(item["name"])
            unique_items.append(item)
    
    # Group by category
    categories = {}
    for item in unique_items:
        cat = item["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)
    
    # Order categories
    ordered_categories = {}
    for cat in CATEGORY_ORDER:
        if cat in categories:
            ordered_categories[cat] = categories[cat]
    # Add any remaining categories not in the predefined order
    for cat in categories:
        if cat not in ordered_categories:
            ordered_categories[cat] = categories[cat]
    
    # Stats
    stats = {
        "total": len(unique_items),
        "weather_based": len([i for i in unique_items if i["is_weather_based"]]),
        "categories": len(ordered_categories),
    }
    
    return {
        "items": unique_items,
        "categories": ordered_categories,
        "stats": stats,
    }
