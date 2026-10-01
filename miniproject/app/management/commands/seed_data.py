from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from app.models import Category, Item


class Command(BaseCommand):
    help = "Populate initial categories and demonstration data for ReuseHub"

    def handle(self, *args, **options):
        self.stdout.write("Seeding ReuseHub platform data...")

        # 1. Default Categories
        categories_data = [
            ("Furniture", "Chairs, tables, desks, bookshelves, sofas, and bedframes."),
            ("Electronics & Appliances", "Monitors, blenders, radios, audio gear, cables, and kitchen appliances."),
            ("Home & Kitchen", "Cookware, tableware, storage organizers, lamps, and decor."),
            ("Tools & DIY Hardware", "Hand tools, power tools, gardening supplies, and scrap materials."),
            ("Books & Media", "Textbooks, novels, records,board games, and magazines."),
            ("Clothing & Linens", "Jackets, clean textiles, blankets, and bags."),
            ("Bicycles & Sports", "Bikes, scooters, repair parts, and sporting gear."),
            ("Repairable Goods", "Items needing minor fixes, parts, soldering, or restoration before reuse."),
        ]

        category_objs = {}
        for name, desc in categories_data:
            cat, created = Category.objects.get_or_create(name=name, defaults={'description': desc})
            category_objs[name] = cat
            if created:
                self.stdout.write(f"  + Created category: {name}")

        # 2. Demo Users
        admin_user, created = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@reusehub.local", "is_staff": True, "is_superuser": True}
        )
        if created:
            admin_user.set_password("admin123")
            admin_user.save()
            self.stdout.write("  + Created admin user (admin / admin123)")

        sarah, created = User.objects.get_or_create(
            username="sarah_c",
            defaults={"email": "sarah@example.com", "first_name": "Sarah", "last_name": "Chen"}
        )
        if created:
            sarah.set_password("user123")
            sarah.save()

        marcus, created = User.objects.get_or_create(
            username="marcus_maker",
            defaults={"email": "marcus@example.com", "first_name": "Marcus", "last_name": "Lee"}
        )
        if created:
            marcus.set_password("user123")
            marcus.save()

        # 3. Sample Listings
        sample_items = [
            {
                "donor": sarah,
                "category": category_objs["Furniture"],
                "title": "Solid Oak Coffee Table (Sturdy)",
                "description": "Moving to a smaller studio apartment. This coffee table has been in my family for 6 years. Sturdy real oak wood with minimal surface wear. Free to whoever can pick it up this weekend!",
                "condition": "GOOD",
                "is_repairable": False,
                "pickup_location": "Oakwood Community Park / 4th St",
                "status": "AVAILABLE",
            },
            {
                "donor": marcus,
                "category": category_objs["Electronics & Appliances"],
                "title": "Vintage Pioneer Stereo Receiver (Needs Fuse / Capacitors)",
                "description": "Great project for audio tinkerers or electrical hobbyists. Turns on but right channel has buzzing sound. Great chassis condition with all knobs intact.",
                "condition": "REPAIRABLE",
                "is_repairable": True,
                "repair_details": "Right speaker channel needs capacitor inspection or fuse replacement. Internal schematics are available online.",
                "pickup_location": "Makerspace Hub, Downtown",
                "status": "AVAILABLE",
            },
            {
                "donor": sarah,
                "category": category_objs["Books & Media"],
                "title": "Box of 15 Classic Fiction & Sci-Fi Novels",
                "description": "Assorted collection including Asimov, Le Guin, and Dickens. Great for summer reading or community micro-library.",
                "condition": "LIKE_NEW",
                "is_repairable": False,
                "pickup_location": "Public Library steps",
                "status": "AVAILABLE",
            },
            {
                "donor": marcus,
                "category": category_objs["Bicycles & Sports"],
                "title": "Classic 10-Speed Commuter Bike (Needs New Inner Tube)",
                "description": "Steel frame road bicycle. Frame and gears are completely solid. Rear tire is flat and needs a $5 inner tube replaced.",
                "condition": "REPAIRABLE",
                "is_repairable": True,
                "repair_details": "Replace rear 700c tube and oil the chain. Brakes and derailleur are in good working order.",
                "pickup_location": "Greenway Bike Trail entrance",
                "status": "AVAILABLE",
            },
            {
                "donor": sarah,
                "category": category_objs["Home & Kitchen"],
                "title": "Cast Iron Dutch Oven 5-Qt",
                "description": "Heavy duty cast iron pot. Cleaned and seasoned with flaxseed oil. Ready to cook soups or sourdough bread.",
                "condition": "GOOD",
                "is_repairable": False,
                "pickup_location": "Northside Farmers Market",
                "status": "GIVEN_AWAY",
            },
            {
                "donor": marcus,
                "category": category_objs["Tools & DIY Hardware"],
                "title": "Corded Jigsaw with Assorted Blades",
                "description": "Reliable 5-amp jigsaw. Tested and works perfectly. Comes with 6 spare wood and metal cutting blades.",
                "condition": "GOOD",
                "is_repairable": False,
                "pickup_location": "Civic Center East Lot",
                "status": "AVAILABLE",
            }
        ]

        for item_data in sample_items:
            item, created = Item.objects.get_or_create(
                title=item_data["title"],
                donor=item_data["donor"],
                defaults=item_data
            )
            if created:
                self.stdout.write(f"  + Added listing: {item.title}")

        self.stdout.write(self.style.SUCCESS("ReuseHub data successfully seeded!"))
