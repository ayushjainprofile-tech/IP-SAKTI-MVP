from retriever import search_tk

query = (
    "Turmeric and Aloe vera in an Ayurvedic herbal skin "
    "formulation, traditional knowledge in India"
)

results = search_tk(query, top_k=5)

print("\nTK RETRIEVER TEST")
print("=" * 70)
print(f"Query: {query}")
print(f"Results: {len(results)}\n")

for i, item in enumerate(results, start=1):
    print(f"[{i}] similarity={item['similarity']}")
    print(f"    source={item['source']}")
    print(f"    page={item.get('page')}")
    print(f"    id={item['id']}")
    print(f"    text={item['page_content'][:300]}")
    print()
