import csv
import os

filename = "confidence_test_cases.csv"

examples_0_percent = [
    {"Product": "Gaming Laptop", "Ingredients": "Silicon, Plastic, Copper", "Purpose": "Play video games", "Category": "Electronics"},
    {"Product": "Latent Powder", "Ingredients": "Latent", "Purpose": "Hidden magic", "Category": "Cosmetic"},
    {"Product": "Iron Nails", "Ingredients": "Iron, Carbon", "Purpose": "Construction", "Category": "Hardware"},
    {"Product": "Smartphone Case", "Ingredients": "Polycarbonate", "Purpose": "Protect phone", "Category": "Accessories"},
    {"Product": "Car Tire", "Ingredients": "Rubber, Steel", "Purpose": "Vehicle movement", "Category": "Automotive"},
    {"Product": "Office Chair", "Ingredients": "Mesh, Foam", "Purpose": "Sitting", "Category": "Furniture"},
    {"Product": "Coffee Mug", "Ingredients": "Ceramic", "Purpose": "Drinking", "Category": "Kitchenware"},
    {"Product": "Plastic Bottle", "Ingredients": "PET", "Purpose": "Store water", "Category": "Packaging"},
    {"Product": "Television", "Ingredients": "Glass, Electronics", "Purpose": "Watch shows", "Category": "Electronics"},
    {"Product": "Shoes", "Ingredients": "Leather, Rubber", "Purpose": "Walking", "Category": "Apparel"},
    {"Product": "Backpack", "Ingredients": "Nylon, Zippers", "Purpose": "Carry items", "Category": "Accessories"},
    {"Product": "Guitar", "Ingredients": "Wood, Steel strings", "Purpose": "Play music", "Category": "Instruments"},
    {"Product": "Bicycle", "Ingredients": "Aluminum, Rubber", "Purpose": "Transport", "Category": "Vehicles"},
    {"Product": "Sunglasses", "Ingredients": "Plastic, Glass", "Purpose": "Eye protection", "Category": "Accessories"},
    {"Product": "Wristwatch", "Ingredients": "Steel, Quartz", "Purpose": "Tell time", "Category": "Jewelry"},
    {"Product": "Scissors", "Ingredients": "Steel", "Purpose": "Cutting", "Category": "Stationery"},
    {"Product": "Notebook", "Ingredients": "Paper", "Purpose": "Writing", "Category": "Stationery"},
    {"Product": "Lightbulb", "Ingredients": "Glass, Tungsten", "Purpose": "Illumination", "Category": "Electronics"},
    {"Product": "Hammer", "Ingredients": "Steel, Wood", "Purpose": "Driving nails", "Category": "Hardware"},
    {"Product": "Toilet Paper", "Ingredients": "Paper", "Purpose": "Hygiene", "Category": "Household"},
    {"Product": "Door Knob", "Ingredients": "Brass", "Purpose": "Open doors", "Category": "Hardware"},
    {"Product": "Window Glass", "Ingredients": "Glass", "Purpose": "Look outside", "Category": "Hardware"},
    {"Product": "Carpet", "Ingredients": "Wool, Synthetic", "Purpose": "Floor covering", "Category": "Home"},
    {"Product": "Sofa", "Ingredients": "Wood, Fabric", "Purpose": "Sitting", "Category": "Furniture"},
    {"Product": "Random Text", "Ingredients": "asdfasdf, qwerqwer", "Purpose": "Nothing", "Category": "None"}
]

examples_20_40_percent = [
    {"Product": "Neem Laptop", "Ingredients": "Neem, Silicon, Plastic", "Purpose": "Play games with neem", "Category": "Electronics"},
    {"Product": "Spicy Face Wash", "Ingredients": "Chilli, Black Pepper", "Purpose": "Wash face", "Category": "Cosmetic"},
    {"Product": "Turmeric Tires", "Ingredients": "Turmeric, Rubber", "Purpose": "Car tires", "Category": "Automotive"},
    {"Product": "Aloe Vera Computer", "Ingredients": "Aloe vera, Aluminum", "Purpose": "Computing", "Category": "Electronics"},
    {"Product": "Tulsi Shoes", "Ingredients": "Tulsi, Leather", "Purpose": "Walking", "Category": "Apparel"},
    {"Product": "Amla Chair", "Ingredients": "Amla, Wood", "Purpose": "Sitting", "Category": "Furniture"},
    {"Product": "Brahmi Mug", "Ingredients": "Brahmi, Ceramic", "Purpose": "Drinking", "Category": "Kitchenware"},
    {"Product": "Ashwagandha Bottle", "Ingredients": "Ashwagandha, PET", "Purpose": "Storing water", "Category": "Packaging"},
    {"Product": "Neem TV", "Ingredients": "Neem, Glass", "Purpose": "Watching TV", "Category": "Electronics"},
    {"Product": "Turmeric Guitar", "Ingredients": "Turmeric, Wood", "Purpose": "Playing music", "Category": "Instruments"},
    {"Product": "Aloe Vera Bike", "Ingredients": "Aloe vera, Steel", "Purpose": "Riding", "Category": "Vehicles"},
    {"Product": "Tulsi Glasses", "Ingredients": "Tulsi, Plastic", "Purpose": "Seeing", "Category": "Accessories"},
    {"Product": "Amla Watch", "Ingredients": "Amla, Quartz", "Purpose": "Timekeeping", "Category": "Jewelry"},
    {"Product": "Brahmi Scissors", "Ingredients": "Brahmi, Steel", "Purpose": "Cutting", "Category": "Stationery"},
    {"Product": "Ashwagandha Book", "Ingredients": "Ashwagandha, Paper", "Purpose": "Reading", "Category": "Stationery"},
    {"Product": "Neem Bulb", "Ingredients": "Neem, Tungsten", "Purpose": "Lighting", "Category": "Electronics"},
    {"Product": "Turmeric Hammer", "Ingredients": "Turmeric, Iron", "Purpose": "Hitting", "Category": "Hardware"},
    {"Product": "Aloe Vera Paper", "Ingredients": "Aloe vera, Pulp", "Purpose": "Wiping", "Category": "Household"},
    {"Product": "Tulsi Knob", "Ingredients": "Tulsi, Brass", "Purpose": "Opening", "Category": "Hardware"},
    {"Product": "Amla Window", "Ingredients": "Amla, Glass", "Purpose": "Viewing", "Category": "Hardware"},
    {"Product": "Brahmi Carpet", "Ingredients": "Brahmi, Wool", "Purpose": "Flooring", "Category": "Home"},
    {"Product": "Ashwagandha Sofa", "Ingredients": "Ashwagandha, Fabric", "Purpose": "Sitting", "Category": "Furniture"},
    {"Product": "Neem Brick", "Ingredients": "Neem, Clay", "Purpose": "Building", "Category": "Construction"},
    {"Product": "Turmeric Paint", "Ingredients": "Turmeric, Acrylic", "Purpose": "Painting walls", "Category": "Home"},
    {"Product": "Aloe Vera Cement", "Ingredients": "Aloe vera, Limestone", "Purpose": "Building", "Category": "Construction"}
]

examples_60_80_percent = [
    {"Product": "Gokshura Supplement", "Ingredients": "Gokshura, Latent", "Purpose": "Energy", "Category": "Ayurvedic Medicine"},
    {"Product": "Shatavri Extract", "Ingredients": "Shatavri, Filler", "Purpose": "Vitality", "Category": "Supplement"},
    {"Product": "Guggul Capsules", "Ingredients": "Guggul, Gelatin", "Purpose": "Joint health", "Category": "Ayurvedic Medicine"},
    {"Product": "Triphala Churna Mix", "Ingredients": "Triphala, Sand", "Purpose": "Digestion", "Category": "Powder"},
    {"Product": "Brahmi Memory Pill", "Ingredients": "Brahmi, Plastic", "Purpose": "Memory", "Category": "Supplement"},
    {"Product": "Neem Face Scrub", "Ingredients": "Neem, Microplastics", "Purpose": "Exfoliation", "Category": "Cosmetic"},
    {"Product": "Turmeric Latte Mix", "Ingredients": "Haldi, Artificial Color", "Purpose": "Drink", "Category": "Food"},
    {"Product": "Ashwagandha Calm", "Ingredients": "Ashwaganda, Sugar", "Purpose": "Stress relief", "Category": "Supplement"},
    {"Product": "Tulsi Cough Syrup", "Ingredients": "Tulsi, High Fructose Corn Syrup", "Purpose": "Cough", "Category": "Medicine"},
    {"Product": "Amla Hair Oil Blend", "Ingredients": "Amla, Mineral Oil", "Purpose": "Hair care", "Category": "Cosmetic"},
    {"Product": "Shilajit Resin Mix", "Ingredients": "Shilajit, Wax", "Purpose": "Strength", "Category": "Ayurvedic Medicine"},
    {"Product": "Giloy Immunity Tablets", "Ingredients": "Giloy, Chalk", "Purpose": "Immunity", "Category": "Supplement"},
    {"Product": "Arjuna Heart Tonic", "Ingredients": "Arjuna, Water", "Purpose": "Heart health", "Category": "Medicine"},
    {"Product": "Haritaki Powder Mix", "Ingredients": "Haritaki, Dirt", "Purpose": "Detox", "Category": "Ayurvedic Medicine"},
    {"Product": "Bibhitaki Extract", "Ingredients": "Bibhitaki, Alcohol", "Purpose": "Respiratory", "Category": "Supplement"},
    {"Product": "Manjistha Blood Purifier", "Ingredients": "Manjistha, Sugar", "Purpose": "Blood purification", "Category": "Ayurvedic Medicine"},
    {"Product": "Punarnava Liver Care", "Ingredients": "Punarnava, Filler", "Purpose": "Liver health", "Category": "Medicine"},
    {"Product": "Bhringraj Hair Tonic", "Ingredients": "Bhringraj, Synthetic Perfume", "Purpose": "Hair growth", "Category": "Cosmetic"},
    {"Product": "Kapikachhu Energy", "Ingredients": "Kapikachhu, Caffeine", "Purpose": "Energy", "Category": "Supplement"},
    {"Product": "Safed Musli Power", "Ingredients": "Safed Musli, Starch", "Purpose": "Strength", "Category": "Ayurvedic Medicine"},
    {"Product": "Yashtimadhu Soothing", "Ingredients": "Yashtimadhu, Honey", "Purpose": "Throat", "Category": "Medicine"},
    {"Product": "Guduchi Fever Care", "Ingredients": "Guduchi, Paracetamol", "Purpose": "Fever", "Category": "Medicine"},
    {"Product": "Vasaka Breath", "Ingredients": "Vasaka, Menthol", "Purpose": "Breathing", "Category": "Supplement"},
    {"Product": "Kutki Liver Detox", "Ingredients": "Kutki, Binder", "Purpose": "Liver detox", "Category": "Ayurvedic Medicine"},
    {"Product": "Chitrak Digestive", "Ingredients": "Chitrak, Salt", "Purpose": "Digestion", "Category": "Medicine"}
]

examples_80_100_percent = [
    {"Product": "Neem Skin Cream", "Ingredients": "Neem", "Purpose": "Treat skin infections", "Category": "Cosmetic"},
    {"Product": "Turmeric Healing Paste", "Ingredients": "Turmeric", "Purpose": "Wound healing", "Category": "Ayurvedic Medicine"},
    {"Product": "Ashwagandha Stress Relief", "Ingredients": "Ashwagandha", "Purpose": "Reduce stress and anxiety", "Category": "Ayurvedic Medicine"},
    {"Product": "Aloe Vera Gel", "Ingredients": "Aloe vera", "Purpose": "Moisturize skin", "Category": "Cosmetic"},
    {"Product": "Tulsi Drops", "Ingredients": "Tulsi", "Purpose": "Boost immunity", "Category": "Ayurvedic Medicine"},
    {"Product": "Amla Juice", "Ingredients": "Amla", "Purpose": "Improve digestion and hair", "Category": "Food"},
    {"Product": "Brahmi Brain Tonic", "Ingredients": "Brahmi", "Purpose": "Enhance memory", "Category": "Ayurvedic Medicine"},
    {"Product": "Triphala Churna", "Ingredients": "Amalaki, Bibhitaki, Haritaki", "Purpose": "Digestive health", "Category": "Ayurvedic Medicine"},
    {"Product": "Shilajit Pure Resin", "Ingredients": "Shilajit", "Purpose": "Increase strength and stamina", "Category": "Ayurvedic Medicine"},
    {"Product": "Giloy Ghanvati", "Ingredients": "Giloy", "Purpose": "Treat fever and boost immunity", "Category": "Ayurvedic Medicine"},
    {"Product": "Arjuna Bark Powder", "Ingredients": "Arjuna", "Purpose": "Cardiovascular health", "Category": "Ayurvedic Medicine"},
    {"Product": "Bhringraj Hair Oil", "Ingredients": "Bhringraj, Coconut Oil", "Purpose": "Prevent hair fall", "Category": "Cosmetic"},
    {"Product": "Manjistha Powder", "Ingredients": "Manjistha", "Purpose": "Blood purification and skin health", "Category": "Ayurvedic Medicine"},
    {"Product": "Punarnava Extract", "Ingredients": "Punarnava", "Purpose": "Kidney and liver support", "Category": "Ayurvedic Medicine"},
    {"Product": "Gokshura Tablets", "Ingredients": "Gokshura", "Purpose": "Urinary tract health", "Category": "Ayurvedic Medicine"},
    {"Product": "Shatavari Granules", "Ingredients": "Shatavari", "Purpose": "Women's health and vitality", "Category": "Ayurvedic Medicine"},
    {"Product": "Guggul Lipid Care", "Ingredients": "Guggul", "Purpose": "Cholesterol management", "Category": "Ayurvedic Medicine"},
    {"Product": "Yashtimadhu Root Powder", "Ingredients": "Yashtimadhu", "Purpose": "Relieve sore throat", "Category": "Ayurvedic Medicine"},
    {"Product": "Safed Musli Churna", "Ingredients": "Safed Musli", "Purpose": "Enhance physical strength", "Category": "Ayurvedic Medicine"},
    {"Product": "Kutki Powder", "Ingredients": "Kutki", "Purpose": "Liver detoxification", "Category": "Ayurvedic Medicine"},
    {"Product": "Chitrakadi Vati", "Ingredients": "Chitrak", "Purpose": "Improve digestion and appetite", "Category": "Ayurvedic Medicine"},
    {"Product": "Vasaka Syrup", "Ingredients": "Vasaka", "Purpose": "Relieve cough and asthma", "Category": "Ayurvedic Medicine"},
    {"Product": "Kapikachhu Seeds Powder", "Ingredients": "Kapikachhu", "Purpose": "Nervous system support", "Category": "Ayurvedic Medicine"},
    {"Product": "Haridra Khand", "Ingredients": "Haridra (Turmeric)", "Purpose": "Allergy relief", "Category": "Ayurvedic Medicine"},
    {"Product": "Neem Oil", "Ingredients": "Neem", "Purpose": "Treat dandruff and lice", "Category": "Cosmetic"}
]

all_examples = []
for ex in examples_0_percent:
    ex["Target_Confidence"] = "0%"
    all_examples.append(ex)
for ex in examples_20_40_percent:
    ex["Target_Confidence"] = "20-40%"
    all_examples.append(ex)
for ex in examples_60_80_percent:
    ex["Target_Confidence"] = "60-80%"
    all_examples.append(ex)
for ex in examples_80_100_percent:
    ex["Target_Confidence"] = "80-100%"
    all_examples.append(ex)

with open(filename, 'w', newline='') as csvfile:
    fieldnames = ['Target_Confidence', 'Product', 'Ingredients', 'Purpose', 'Category']
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    for row in all_examples:
        writer.writerow(row)

print(f"Created {filename} with 100 test cases.")
