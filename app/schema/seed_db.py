"""
Database Seed Script
Run with: python -m scripts.seed_db
Populates: super admin, destinations, itinerary blocks, hotels, vehicles, activities, seasonal pricing
"""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from app.config import settings
from app.database import AsyncSessionLocal, create_all_tables
from app.models import (
    Activity, Destination, Hotel, ItineraryBlock, MealPlanCode,
    MealPlanRate, RoomType, Season, SeasonalPricingRule,
    User, UserRole, Vehicle, VehicleSeasonalRate, Agent, MarkupType,
)
from app.services.auth_service import hash_password


async def seed():
    print("🌱 Creating tables...")
    await create_all_tables()

    async with AsyncSessionLocal() as db:
        # ── Super Admin ────────────────────────────────────────────────────────
        from sqlalchemy import select
        existing = await db.execute(select(User).where(User.email == "admin@wanderkashmir.com"))
        if not existing.scalar_one_or_none():
            admin = User(
                email="admin@wanderkashmir.com",
                hashed_password=hash_password("Admin@1234"),
                full_name="Super Admin",
                role=UserRole.SUPER_ADMIN,
                is_active=True,
                is_verified=True,
            )
            db.add(admin)
            await db.flush()
            print(f"  ✅ Admin created: admin@wanderkashmir.com / Admin@1234")

        # ── Demo Agent ─────────────────────────────────────────────────────────
        existing_agent = await db.execute(select(User).where(User.email == "demo@wanderkashmir.com"))
        if not existing_agent.scalar_one_or_none():
            agent_user = User(
                email="demo@wanderkashmir.com",
                hashed_password=hash_password("demo1234"),
                full_name="Demo Agent",
                role=UserRole.AGENT,
                is_active=True,
                is_verified=True,
            )
            db.add(agent_user)
            await db.flush()
            agent_profile = Agent(
                user_id=agent_user.id,
                agency_name="Sunrise Travels, Delhi",
                city="Delhi",
                state="Delhi",
                markup_type=MarkupType.PERCENTAGE,
                markup_value=Decimal("15.00"),
                show_price_breakdown=False,
                is_approved=True,
            )
            db.add(agent_profile)
            await db.flush()
            print(f"  ✅ Agent created: demo@wanderkashmir.com / demo1234")

        # ── Seasonal Pricing ───────────────────────────────────────────────────
        seasonal_rules = [
            {"season": Season.PEAK, "label": "Peak Summer (Apr–Jun)", "multiplier": Decimal("1.30"), "date_from": "04-01", "date_to": "06-30"},
            {"season": Season.SUMMER, "label": "Regular Summer (Jul–Sep)", "multiplier": Decimal("1.00"), "date_from": "07-01", "date_to": "09-30"},
            {"season": Season.WINTER, "label": "Winter (Dec–Mar)", "multiplier": Decimal("1.20"), "date_from": "12-01", "date_to": "03-31"},
            {"season": Season.NEW_YEAR, "label": "New Year Special", "multiplier": Decimal("1.60"), "date_from": "12-28", "date_to": "01-03"},
            {"season": Season.LONG_WEEKEND, "label": "Long Weekend Surcharge", "multiplier": Decimal("1.25")},
            {"season": Season.OFF_SEASON, "label": "Off Season", "multiplier": Decimal("0.90")},
        ]
        for rule_data in seasonal_rules:
            existing_rule = await db.execute(select(SeasonalPricingRule).where(SeasonalPricingRule.season == rule_data["season"]))
            if not existing_rule.scalar_one_or_none():
                db.add(SeasonalPricingRule(**rule_data, is_active=True))
        await db.flush()
        print("  ✅ Seasonal pricing rules seeded")

        # ── Destinations ───────────────────────────────────────────────────────
        dest_data = [
            {"name": "Srinagar", "slug": "srinagar", "region": "Kashmir Valley", "highlights": ["Dal Lake", "Mughal Gardens", "Houseboats", "Hazratbal Mosque"], "sort_order": 1},
            {"name": "Gulmarg", "slug": "gulmarg", "region": "Baramulla", "highlights": ["Gondola Phase 1 & 2", "Skiing", "Snow Activities", "Alpine Meadows"], "sort_order": 2},
            {"name": "Pahalgam", "slug": "pahalgam", "region": "Anantnag", "highlights": ["Lidder River", "Aru Valley", "Betaab Valley", "Chandanwari"], "sort_order": 3},
            {"name": "Sonmarg", "slug": "sonmarg", "region": "Ganderbal", "highlights": ["Thajiwas Glacier", "Sindh River", "Alpine Meadows"], "sort_order": 4},
            {"name": "Doodhpathri", "slug": "doodhpathri", "region": "Budgam", "highlights": ["Meadows", "Waterfalls", "Pine Forest"], "sort_order": 5},
        ]
        dest_map = {}
        for d in dest_data:
            existing_dest = await db.execute(select(Destination).where(Destination.slug == d["slug"]))
            dest_obj = existing_dest.scalar_one_or_none()
            if not dest_obj:
                dest_obj = Destination(**d, is_active=True)
                db.add(dest_obj)
                await db.flush()
            dest_map[d["slug"]] = dest_obj
        print("  ✅ Destinations seeded")

        # ── Itinerary Blocks ───────────────────────────────────────────────────
        itinerary_data = [
            # Day 1 — Arrival Options
            {"title": "Arrival Srinagar — Dal Lake & City Sightseeing", "day_number": 1, "departs_from": "arrival", "overnight_slug": "srinagar", "icon": "🏔", "duration_label": "Full Day", "highlights": ["Dal Lake Shikara", "Mughal Gardens", "Hazratbal Mosque"], "description": "Arrive at Srinagar Airport. Meet & greet by our representative. Transfer to houseboat or hotel on Dal Lake. Check-in and freshen up. Afternoon shikara ride on the world-famous Dal Lake. Visit Nishat Bagh, Shalimar Bagh, and Chashme Shahi (Mughal Gardens). Evening at leisure at Boulevard Road. Overnight in Srinagar."},
            {"title": "Arrival Srinagar — Transfer to Pahalgam", "day_number": 1, "departs_from": "arrival", "overnight_slug": "pahalgam", "icon": "🌲", "duration_label": "Full Day", "highlights": ["Awantipora Ruins", "Lidder River Walk", "Pine Forest"], "description": "Arrive at Srinagar Airport. Transfer directly to Pahalgam — the Valley of Shepherds (95 km, ~3 hours). En route visit the ruins of Awantipora, a 9th-century Hindu temple. Arrive Pahalgam, check-in at hotel. Evening walk along the scenic Lidder River. Overnight in Pahalgam."},
            {"title": "Arrival Srinagar — Transfer to Gulmarg", "day_number": 1, "departs_from": "arrival", "overnight_slug": "gulmarg", "icon": "⛷", "duration_label": "Full Day", "highlights": ["Gondola Phase 1", "Meadow Walk", "Snow Views"], "description": "Arrive at Srinagar Airport. Transfer directly to Gulmarg — Asia's premier ski resort (56 km, ~2 hours). Check-in at hotel. Afternoon Gondola Phase 1 ride to Kongdoori. Enjoy meadow walks and snow activities. Overnight in Gulmarg."},
            # Day 2 — from Srinagar
            {"title": "Srinagar — Gulmarg Day Excursion", "day_number": 2, "departs_from": "srinagar", "overnight_slug": "srinagar", "icon": "⛷", "duration_label": "Full Day", "highlights": ["Gondola Phase 1 & 2", "Apharwat Peak", "Snow Activities"], "description": "After breakfast, drive to Gulmarg (56 km, ~2 hrs). Board the world's highest gondola — Phase 1 to Kongdoori and Phase 2 to Apharwat Peak (13,500 ft). Enjoy skiing, snow sledging, or simply marvel at the breathtaking panoramic views. Return to Srinagar by evening. Overnight in Srinagar."},
            {"title": "Srinagar — Sonmarg Day Trip", "day_number": 2, "departs_from": "srinagar", "overnight_slug": "srinagar", "icon": "🏔", "duration_label": "Full Day", "highlights": ["Thajiwas Glacier", "Sindh River", "Alpine Wildflowers"], "description": "After breakfast, drive to Sonmarg — Meadow of Gold (84 km, ~3 hrs). Visit the stunning Thajiwas Glacier by local transport or pony. Enjoy the pristine Sindh River, wildflower meadows, and majestic mountain views. Return to Srinagar by evening. Overnight in Srinagar."},
            {"title": "Srinagar — Local City Sightseeing", "day_number": 2, "departs_from": "srinagar", "overnight_slug": "srinagar", "icon": "🕌", "duration_label": "Full Day", "highlights": ["Shankaracharya Temple", "Old City", "Lal Chowk", "Floating Vegetable Market"], "description": "Full day Srinagar city tour. Morning visit to Shankaracharya Temple for panoramic views of the city and Dal Lake. Visit the old city — Jamia Masjid mosque, Shah-i-Hamdan shrine, Rozabal Shrine. Afternoon at Dal Lake floating market. Evening shopping at Lal Chowk. Overnight in Srinagar."},
            {"title": "Srinagar — Transfer to Pahalgam", "day_number": 2, "departs_from": "srinagar", "overnight_slug": "pahalgam", "icon": "🌿", "duration_label": "Full Day", "highlights": ["Betaab Valley", "Aru Valley", "Lidder River"], "description": "After breakfast, check-out and drive to Pahalgam (95 km, ~3 hrs). En route, stop at Awantipora ruins. Arrive Pahalgam and check-in. Afternoon visit to Betaab Valley and Aru Valley. Evening stroll along the Lidder River. Overnight in Pahalgam."},
            # Day 2 — from Pahalgam
            {"title": "Pahalgam — Aru Valley & Betaab Valley", "day_number": 2, "departs_from": "pahalgam", "overnight_slug": "pahalgam", "icon": "🌿", "duration_label": "Full Day", "highlights": ["Aru Valley", "Betaab Valley", "Chandanwari"], "description": "Full day excursions from Pahalgam. Morning visit to Aru Valley (11 km), a serene meadow surrounded by snow-capped peaks. Afternoon to Betaab Valley, named after the Bollywood film shot here. Optional visit to Chandanwari — the base camp for Amarnath Yatra. Pony rides available. Overnight in Pahalgam."},
            {"title": "Pahalgam — Transfer to Gulmarg via Srinagar", "day_number": 2, "departs_from": "pahalgam", "overnight_slug": "gulmarg", "icon": "⛷", "duration_label": "Full Day", "highlights": ["Gondola Ride", "Srinagar Stopover", "Snow Activities"], "description": "After breakfast, drive from Pahalgam to Gulmarg via Srinagar (~5 hrs total). En route short sightseeing in Srinagar. Arrive Gulmarg, check-in. Afternoon Gondola Phase 1 ride. Overnight in Gulmarg."},
            # Day 2 — from Gulmarg
            {"title": "Gulmarg — Full Day Skiing & Snow Activities", "day_number": 2, "departs_from": "gulmarg", "overnight_slug": "gulmarg", "icon": "🎿", "duration_label": "Full Day", "highlights": ["Gondola Phase 1 & 2", "Ski Lessons", "Snow Sledging"], "description": "Full day in Gulmarg. Gondola Phase 1 and Phase 2 to Apharwat Peak. Professional skiing lessons available (equipment on hire). Snow sledging, snowball fights, and ATV rides on snow. Return to hotel. Overnight in Gulmarg."},
            {"title": "Gulmarg — Transfer to Srinagar", "day_number": 2, "departs_from": "gulmarg", "overnight_slug": "srinagar", "icon": "🏙", "duration_label": "Full Day", "highlights": ["Gondola Morning Ride", "Local Market Shopping", "Dal Lake Evening"], "description": "Morning Gondola ride before check-out. Drive to Srinagar (56 km, ~2 hrs). Afternoon free for shopping — Kashmiri shawls, carpets, saffron, and dry fruits at Polo View Market. Evening Shikara ride on Dal Lake. Overnight in Srinagar."},
            # Day 3 — from Srinagar
            {"title": "Srinagar — Transfer to Pahalgam Full Day", "day_number": 3, "departs_from": "srinagar", "overnight_slug": "pahalgam", "icon": "🌲", "duration_label": "Full Day", "highlights": ["Saffron Fields", "Pampore", "Lidder Valley"], "description": "After breakfast, drive to Pahalgam. En route visit Pampore — the Saffron town of Kashmir. Arrive Pahalgam, check-in. Afternoon free to explore the valley or optional pony rides. Overnight in Pahalgam."},
            {"title": "Srinagar — Doodhpathri Excursion", "day_number": 3, "departs_from": "srinagar", "overnight_slug": "srinagar", "icon": "🌸", "duration_label": "Full Day", "highlights": ["Milk Spring", "Meadows", "Waterfalls", "Untouched Nature"], "description": "Day trip to Doodhpathri — the Valley of Milk (42 km). Known for its milky white spring water streams, lush meadows, and waterfalls. Relatively unexplored and pristine. Pack lunch or enjoy local dhabas. Return to Srinagar. Overnight in Srinagar."},
            # Day 3 — from Pahalgam
            {"title": "Pahalgam — Transfer to Srinagar & Shopping", "day_number": 3, "departs_from": "pahalgam", "overnight_slug": "srinagar", "icon": "🛍", "duration_label": "Full Day", "highlights": ["Handicraft Shopping", "Lal Chowk", "Kashmiri Wazwan Dinner"], "description": "After breakfast, check-out from Pahalgam. Drive to Srinagar (2.5 hrs). Afternoon visit to Government Emporiums, Polo View Market, and Handicraft Cooperative. Buy Kashmiri shawls, pashmina, carpets, and local saffron. Optional authentic Wazwan dinner. Overnight in Srinagar."},
            # Departure Day
            {"title": "Departure — Fond Farewell to Kashmir", "day_number": 99, "departs_from": "srinagar", "overnight_slug": None, "icon": "✈", "duration_label": "Half Day", "highlights": ["Sunrise Shikara", "Dal Lake Breakfast", "Airport Drop"], "description": "Wake up early for an optional sunrise Shikara ride on Dal Lake. Leisurely breakfast at the hotel. Check-out and transfer to Srinagar International Airport. Bid farewell to Kashmir with beautiful memories. Tour concludes."},
        ]

        existing_itin = await db.execute(select(ItineraryBlock))
        if not existing_itin.scalars().all():
            for itin in itinerary_data:
                overnight_id = None
                overnight_slug = itin.get("overnight_slug")
                if overnight_slug and overnight_slug in dest_map:
                    overnight_id = dest_map[overnight_slug].id
                block = ItineraryBlock(
                    title=itin["title"],
                    description=itin["description"],
                    day_number=itin["day_number"],
                    departs_from=itin["departs_from"],
                    overnight_destination_id=overnight_id,
                    overnight_slug=overnight_slug,
                    highlights=itin["highlights"],
                    duration_label=itin["duration_label"],
                    icon=itin["icon"],
                    tags=[itin["departs_from"], overnight_slug or "departure"],
                    is_active=True,
                )
                db.add(block)
            await db.flush()
        print("  ✅ Itinerary blocks seeded")

        # ── Hotels ─────────────────────────────────────────────────────────────
        existing_hotels = await db.execute(select(Hotel))
        if not existing_hotels.scalars().all():
            hotel_data = [
                {"name": "The Lalit Grand Palace Srinagar", "slug": "srinagar", "category": "5 Star Deluxe", "stars": 5,
                 "description": "Former palace of the Maharaja of J&K, now a heritage luxury hotel with stunning Dal Lake views.",
                 "amenities": ["Spa", "Pool", "Heritage Restaurant", "Lake View", "WiFi", "Gym", "24hr Room Service"],
                 "room_types": [
                     {"name": "Deluxe Room", "rates": {MealPlanCode.EP: 8500, MealPlanCode.CP: 9500, MealPlanCode.MAP: 11500, MealPlanCode.AP: 13500}, "extra_bed": 2500},
                     {"name": "Luxury Room", "rates": {MealPlanCode.EP: 11000, MealPlanCode.CP: 12500, MealPlanCode.MAP: 14500, MealPlanCode.AP: 16500}, "extra_bed": 3000},
                     {"name": "Suite", "rates": {MealPlanCode.EP: 18000, MealPlanCode.CP: 20000, MealPlanCode.MAP: 23000, MealPlanCode.AP: 26000}, "extra_bed": 4000},
                 ]},
                {"name": "Houseboat New Beautiful Star (Dal Lake)", "slug": "srinagar", "category": "Premium Houseboat", "stars": 4,
                 "description": "Authentic carved cedar wood houseboat on serene Dal Lake with traditional Kashmiri hospitality.",
                 "amenities": ["Dal Lake View", "Traditional Décor", "Home Meals", "Shikara Pick-up", "WiFi"],
                 "room_types": [
                     {"name": "Standard Cabin", "rates": {MealPlanCode.EP: 4500, MealPlanCode.CP: 5200, MealPlanCode.MAP: 6500, MealPlanCode.AP: 7800}, "extra_bed": 1500},
                     {"name": "Deluxe Cabin", "rates": {MealPlanCode.EP: 6500, MealPlanCode.CP: 7500, MealPlanCode.MAP: 9000, MealPlanCode.AP: 10500}, "extra_bed": 2000},
                 ]},
                {"name": "Centaur Lake View Hotel", "slug": "srinagar", "category": "5 Star", "stars": 5,
                 "description": "Iconic hotel overlooking Dal Lake with contemporary amenities and panoramic views.",
                 "amenities": ["Lake View", "Spa", "Multiple Restaurants", "Pool", "WiFi", "Conference Hall"],
                 "room_types": [
                     {"name": "Deluxe Room", "rates": {MealPlanCode.EP: 7200, MealPlanCode.CP: 8500, MealPlanCode.MAP: 10000, MealPlanCode.AP: 12000}, "extra_bed": 2200},
                     {"name": "Lake View Suite", "rates": {MealPlanCode.EP: 14000, MealPlanCode.CP: 16000, MealPlanCode.MAP: 19000, MealPlanCode.AP: 22000}, "extra_bed": 3500},
                 ]},
                {"name": "Hotel Pine Spring Pahalgam", "slug": "pahalgam", "category": "4 Star", "stars": 4,
                 "description": "Nestled among pine forests on the banks of Lidder River with stunning valley views.",
                 "amenities": ["River View", "Pine Forest", "Restaurant", "Bonfire Area", "WiFi"],
                 "room_types": [
                     {"name": "Standard Room", "rates": {MealPlanCode.EP: 3500, MealPlanCode.CP: 4200, MealPlanCode.MAP: 5500, MealPlanCode.AP: 6800}, "extra_bed": 1200},
                     {"name": "Deluxe River View", "rates": {MealPlanCode.EP: 5000, MealPlanCode.CP: 6000, MealPlanCode.MAP: 7500, MealPlanCode.AP: 9000}, "extra_bed": 1500},
                     {"name": "Suite", "rates": {MealPlanCode.EP: 8000, MealPlanCode.CP: 9500, MealPlanCode.MAP: 12000, MealPlanCode.AP: 14500}, "extra_bed": 2500},
                 ]},
                {"name": "Highlands Park Hotel Gulmarg", "slug": "gulmarg", "category": "4 Star", "stars": 4,
                 "description": "Colonial-era property with magnificent snow-clad mountain views and skiing access.",
                 "amenities": ["Mountain Views", "Ski Equipment Hire", "Restaurant", "Ski-In/Out", "WiFi", "Fireplace"],
                 "room_types": [
                     {"name": "Standard Room", "rates": {MealPlanCode.EP: 4800, MealPlanCode.CP: 5800, MealPlanCode.MAP: 7200, MealPlanCode.AP: 8500}, "extra_bed": 1500},
                     {"name": "Deluxe Mountain View", "rates": {MealPlanCode.EP: 6500, MealPlanCode.CP: 7800, MealPlanCode.MAP: 9500, MealPlanCode.AP: 11000}, "extra_bed": 2000},
                 ]},
            ]

            for h in hotel_data:
                dest = dest_map.get(h["slug"])
                if not dest:
                    continue
                hotel = Hotel(
                    name=h["name"], destination_id=dest.id, category=h["category"],
                    stars=h["stars"], description=h["description"], amenities=h["amenities"],
                    rating=Decimal("4.5"), review_count=200, extra_bed_available=True, is_active=True,
                )
                db.add(hotel)
                await db.flush()
                for rt_data in h["room_types"]:
                    rt = RoomType(hotel_id=hotel.id, name=rt_data["name"], max_occupancy=2, extra_bed_rate=Decimal(str(rt_data["extra_bed"])))
                    db.add(rt)
                    await db.flush()
                    for mp, rate in rt_data["rates"].items():
                        db.add(MealPlanRate(room_type_id=rt.id, meal_plan=mp, rate_per_night=Decimal(str(rate))))
            await db.flush()
        print("  ✅ Hotels seeded")

        # ── Vehicles ───────────────────────────────────────────────────────────
        existing_vehicles = await db.execute(select(Vehicle))
        if not existing_vehicles.scalars().all():
            vehicle_data = [
                {"vehicle_type": "Sedan", "models": "Swift Dzire / Honda Amaze / Maruti Ciaz", "capacity_pax": 4, "luggage_capacity": "3 Medium Bags", "icon_emoji": "🚗", "per_day_rate": Decimal("2200"), "per_km_rate": Decimal("14"), "airport_transfer_rate": Decimal("800"), "suitable_for": ["Couples", "Solo Travelers", "Small Families"], "seasonal": {Season.WINTER: 500, Season.PEAK: 800}},
                {"vehicle_type": "Ertiga", "models": "Maruti Ertiga / Mahindra Marazzo", "capacity_pax": 6, "luggage_capacity": "4 Medium Bags", "icon_emoji": "🚙", "per_day_rate": Decimal("2800"), "per_km_rate": Decimal("16"), "airport_transfer_rate": Decimal("1000"), "suitable_for": ["Families", "Small Groups"], "seasonal": {Season.WINTER: 600, Season.PEAK: 1000}},
                {"vehicle_type": "Innova", "models": "Toyota Innova", "capacity_pax": 7, "luggage_capacity": "5 Medium Bags", "icon_emoji": "🚐", "per_day_rate": Decimal("3500"), "per_km_rate": Decimal("20"), "airport_transfer_rate": Decimal("1400"), "suitable_for": ["Large Families", "Groups", "Comfortable Travel"], "seasonal": {Season.WINTER: 800, Season.PEAK: 1200}},
                {"vehicle_type": "Innova Crysta", "models": "Toyota Innova Crysta (Premium)", "capacity_pax": 7, "luggage_capacity": "6 Medium Bags", "icon_emoji": "🚐", "per_day_rate": Decimal("4200"), "per_km_rate": Decimal("22"), "airport_transfer_rate": Decimal("1700"), "suitable_for": ["Premium Groups", "Corporate", "Luxury Travel"], "seasonal": {Season.WINTER: 1000, Season.PEAK: 1500}},
                {"vehicle_type": "Tempo Traveller", "models": "Force Traveller 12/14/17 Seater", "capacity_pax": 15, "luggage_capacity": "10+ Bags", "icon_emoji": "🚌", "per_day_rate": Decimal("6500"), "per_km_rate": Decimal("28"), "airport_transfer_rate": Decimal("2500"), "suitable_for": ["Large Groups", "Pilgrimages", "Corporate Tours"], "seasonal": {Season.WINTER: 1500, Season.PEAK: 2200}},
                {"vehicle_type": "Urbania", "models": "Force Urbania Luxury Coach", "capacity_pax": 18, "luggage_capacity": "15+ Bags", "icon_emoji": "🚌", "per_day_rate": Decimal("9500"), "per_km_rate": Decimal("35"), "airport_transfer_rate": Decimal("3500"), "suitable_for": ["Premium Groups", "MICE", "Luxury Coach"], "seasonal": {Season.WINTER: 2000, Season.PEAK: 3000}},
            ]
            for i, v in enumerate(vehicle_data):
                seasonal = v.pop("seasonal")
                vehicle = Vehicle(**v, sort_order=i, is_active=True)
                db.add(vehicle)
                await db.flush()
                for season, surcharge in seasonal.items():
                    db.add(VehicleSeasonalRate(vehicle_id=vehicle.id, season=season, surcharge_per_day=Decimal(str(surcharge))))
            await db.flush()
        print("  ✅ Vehicles seeded")

        # ── Activities ─────────────────────────────────────────────────────────
        existing_acts = await db.execute(select(Activity))
        if not existing_acts.scalars().all():
            activities = [
                {"name": "Gondola Phase 1 (Kongdoori)", "slug": "gulmarg", "category": "Adventure", "base_price": Decimal("800"), "duration_label": "2 hours"},
                {"name": "Gondola Phase 2 (Apharwat Peak)", "slug": "gulmarg", "category": "Adventure", "base_price": Decimal("1200"), "duration_label": "3 hours"},
                {"name": "Shikara Ride (1 hour)", "slug": "srinagar", "category": "Leisure", "base_price": Decimal("600"), "duration_label": "1 hour"},
                {"name": "Shikara Ride Sunset (2 hrs)", "slug": "srinagar", "category": "Leisure", "base_price": Decimal("1200"), "duration_label": "2 hours"},
                {"name": "Pony Ride — Pahalgam", "slug": "pahalgam", "category": "Adventure", "base_price": Decimal("500"), "duration_label": "1 hour"},
                {"name": "Pony Ride — Gulmarg Meadow", "slug": "gulmarg", "category": "Adventure", "base_price": Decimal("600"), "duration_label": "1 hour"},
                {"name": "ATV Ride — Pahalgam", "slug": "pahalgam", "category": "Adventure", "base_price": Decimal("800"), "duration_label": "30 minutes"},
                {"name": "Snow Sledging", "slug": "gulmarg", "category": "Adventure", "base_price": Decimal("400"), "duration_label": "1 hour"},
                {"name": "Thajiwas Glacier Pony — Sonmarg", "slug": "sonmarg", "category": "Adventure", "base_price": Decimal("700"), "duration_label": "Half Day"},
                {"name": "Kashmiri Cooking Class", "slug": "srinagar", "category": "Cultural", "base_price": Decimal("1500"), "duration_label": "3 hours"},
                {"name": "Photography Tour — Old Srinagar", "slug": "srinagar", "category": "Cultural", "base_price": Decimal("2000"), "duration_label": "Half Day"},
            ]
            for act in activities:
                dest = dest_map.get(act.pop("slug"))
                dest_id = dest.id if dest else None
                db.add(Activity(destination_id=dest_id, is_active=True, sort_order=0, **act))
            await db.flush()
        print("  ✅ Activities seeded")

        await db.commit()
        print("\n✅ Database seeded successfully!")
        print(f"   Admin: admin@wanderkashmir.com / Admin@1234")
        print(f"   Agent: demo@wanderkashmir.com / demo1234")


if __name__ == "__main__":
    asyncio.run(seed())