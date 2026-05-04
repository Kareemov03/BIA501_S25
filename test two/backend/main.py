import pandas as pd
import numpy as np
import random
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Hybrid GA Recommender System API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────
# DATA LOADING
# ──────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_new")

df_users = pd.read_excel(os.path.join(DATA_DIR, "users.xlsx"))
df_products = pd.read_excel(os.path.join(DATA_DIR, "products.xlsx"))
df_ratings = pd.read_excel(os.path.join(DATA_DIR, "ratings.xlsx"))
df_behavior = pd.read_excel(os.path.join(DATA_DIR, "behavior_15500.xlsx"))

products_list = df_products["product_id"].tolist()
product_dict = df_products.set_index("product_id").to_dict("index")
all_user_ids = df_users["user_id"].tolist()

# ──────────────────────────────────────────────
# PRECOMPUTE: User-Product Rating Matrix (sparse dict)
# ──────────────────────────────────────────────
user_rating_vectors = {}
for uid in all_user_ids:
    user_rating_vectors[uid] = {}

for _, row in df_ratings.iterrows():
    uid, pid, rating = int(row["user_id"]), int(row["product_id"]), float(row["rating"])
    user_rating_vectors[uid][pid] = rating

# ──────────────────────────────────────────────
# PRECOMPUTE: Global product popularity scores
# ──────────────────────────────────────────────
product_popularity = {}
for pid in products_list:
    b = df_behavior[df_behavior["product_id"] == pid]
    score = b["viewed"].sum() * 1 + b["clicked"].sum() * 3 + b["purchased"].sum() * 10
    r = df_ratings[df_ratings["product_id"] == pid]
    if len(r) > 0:
        score += r["rating"].mean() * 5
    product_popularity[pid] = score

# ──────────────────────────────────────────────
# COLLABORATIVE FILTERING: Cosine Similarity
# ──────────────────────────────────────────────
def cosine_similarity(vec_a: dict, vec_b: dict) -> float:
    """Compute cosine similarity between two sparse rating vectors."""
    common = set(vec_a.keys()) & set(vec_b.keys())
    if not common:
        return 0.0
    dot = sum(vec_a[k] * vec_b[k] for k in common)
    mag_a = np.sqrt(sum(v ** 2 for v in vec_a.values()))
    mag_b = np.sqrt(sum(v ** 2 for v in vec_b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def get_similar_users(user_id: int, top_k: int = 10) -> list:
    """Find top-K most similar users based on cosine similarity of ratings."""
    target_vec = user_rating_vectors.get(user_id, {})
    if not target_vec:
        return []
    similarities = []
    for uid in all_user_ids:
        if uid == user_id:
            continue
        sim = cosine_similarity(target_vec, user_rating_vectors.get(uid, {}))
        if sim > 0:
            similarities.append((uid, sim))
    similarities.sort(key=lambda x: x[1], reverse=True)
    return similarities[:top_k]


def collaborative_score(user_id: int, product_id: int, similar_users: list) -> float:
    """Score a product based on how similar users rated it."""
    if not similar_users:
        return 0.0
    weighted_sum = 0.0
    weight_total = 0.0
    for sim_uid, sim_val in similar_users:
        rating = user_rating_vectors.get(sim_uid, {}).get(product_id)
        if rating is not None:
            weighted_sum += sim_val * rating
            weight_total += sim_val
    if weight_total == 0:
        return 0.0
    return weighted_sum / weight_total


# ──────────────────────────────────────────────
# USER PREFERENCE ANALYSIS
# ──────────────────────────────────────────────
def get_user_preferences(user_id: int):
    """Analyze user behavior and ratings to build a preference profile."""
    category_prefs = {}
    purchased_products = set()
    price_list = []

    u_behavior = df_behavior[df_behavior["user_id"] == user_id]
    for _, row in u_behavior.iterrows():
        pid = int(row["product_id"])
        if pid not in product_dict:
            continue
        cat = product_dict[pid]["category"]
        weight = row["viewed"] * 1 + row["clicked"] * 3 + row["purchased"] * 10
        category_prefs[cat] = category_prefs.get(cat, 0) + weight
        if row["purchased"] > 0:
            purchased_products.add(pid)
            price_list.append(product_dict[pid]["price"])

    u_ratings = df_ratings[df_ratings["user_id"] == user_id]
    for _, row in u_ratings.iterrows():
        pid = int(row["product_id"])
        if pid not in product_dict:
            continue
        cat = product_dict[pid]["category"]
        category_prefs[cat] = category_prefs.get(cat, 0) + row["rating"] * 2

    avg_price = np.mean(price_list) if price_list else 500
    price_std = np.std(price_list) if len(price_list) > 1 else 300

    return category_prefs, purchased_products, avg_price, price_std


# ──────────────────────────────────────────────
# HYBRID GENETIC ALGORITHM
# ──────────────────────────────────────────────
class HybridGeneticAlgorithm:
    def __init__(
        self,
        user_id: int,
        pop_size: int = 30,
        chromosome_length: int = 6,
        generations: int = 20,
        initial_mutation_rate: float = 0.3,
        final_mutation_rate: float = 0.05,
        tournament_size: int = 3,
        elite_count: int = 2,
    ):
        self.user_id = user_id
        self.pop_size = pop_size
        self.chromosome_length = chromosome_length
        self.generations = generations
        self.initial_mutation_rate = initial_mutation_rate
        self.final_mutation_rate = final_mutation_rate
        self.tournament_size = tournament_size
        self.elite_count = elite_count

        # User analysis
        self.cat_prefs, self.purchased, self.avg_price, self.price_std = get_user_preferences(user_id)
        self.similar_users = get_similar_users(user_id, top_k=10)

    def adaptive_mutation_rate(self, gen: int) -> float:
        """Linearly decrease mutation rate from initial to final over generations."""
        ratio = gen / max(self.generations - 1, 1)
        return self.initial_mutation_rate - ratio * (self.initial_mutation_rate - self.final_mutation_rate)

    def fitness(self, chromosome: list) -> float:
        score = 0.0
        categories = set()

        for pid in chromosome:
            info = product_dict[pid]
            cat = info["category"]
            price = info["price"]

            # 1. Category preference (personal)
            score += self.cat_prefs.get(cat, 0) * 1.5

            # 2. Collaborative filtering score (social)
            cf = collaborative_score(self.user_id, pid, self.similar_users)
            score += cf * 20

            # 3. Price sensitivity — Gaussian proximity to user's avg price
            if self.price_std > 0:
                price_fit = np.exp(-0.5 * ((price - self.avg_price) / self.price_std) ** 2)
            else:
                price_fit = 1.0 if abs(price - self.avg_price) < 200 else 0.3
            score += price_fit * 30

            # 4. Global popularity (slight boost)
            score += product_popularity.get(pid, 0) * 0.05

            # 5. Penalty: already purchased
            if pid in self.purchased:
                score -= 500

            categories.add(cat)

        # 6. Diversity bonus — more unique categories = better
        score += len(categories) * 40

        # 7. Uniqueness constraint — penalize duplicate products
        unique_count = len(set(chromosome))
        if unique_count < len(chromosome):
            score -= (len(chromosome) - unique_count) * 1000

        return score

    def create_individual(self) -> list:
        return random.sample(products_list, self.chromosome_length)

    def tournament_select(self, population: list, fitnesses: list) -> list:
        """Select one individual via tournament selection."""
        indices = random.sample(range(len(population)), self.tournament_size)
        best_idx = max(indices, key=lambda i: fitnesses[i])
        return list(population[best_idx])  # return a copy

    def uniform_crossover(self, parent1: list, parent2: list) -> tuple:
        """Each gene is independently chosen from either parent."""
        child1, child2 = [], []
        for i in range(self.chromosome_length):
            if random.random() < 0.5:
                child1.append(parent1[i])
                child2.append(parent2[i])
            else:
                child1.append(parent2[i])
                child2.append(parent1[i])
        return child1, child2

    def mutate(self, chromosome: list, mutation_rate: float) -> list:
        """Mutate each gene independently with the given mutation rate."""
        for i in range(len(chromosome)):
            if random.random() < mutation_rate:
                chromosome[i] = random.choice(products_list)
        return chromosome

    def run(self) -> list:
        population = [self.create_individual() for _ in range(self.pop_size)]
        history = []

        for gen in range(self.generations):
            # Evaluate fitness for all individuals
            fitnesses = [self.fitness(ind) for ind in population]

            # Sort by fitness (descending)
            paired = sorted(zip(population, fitnesses), key=lambda x: x[1], reverse=True)
            population = [ind for ind, _ in paired]
            fitnesses = [f for _, f in paired]

            best_ind = population[0]
            best_score = fitnesses[0]
            avg_score = np.mean(fitnesses)

            # Record generation history
            best_products = [
                {
                    "id": pid,
                    "category": product_dict[pid]["category"],
                    "price": product_dict[pid]["price"],
                }
                for pid in best_ind
            ]
            history.append(
                {
                    "generation": gen + 1,
                    "best_score": round(best_score, 2),
                    "avg_score": round(avg_score, 2),
                    "mutation_rate": round(self.adaptive_mutation_rate(gen), 3),
                    "recommendations": best_products,
                }
            )

            # === BUILD NEXT GENERATION ===
            next_gen = []

            # Elitism: carry forward top individuals unchanged
            for i in range(self.elite_count):
                next_gen.append(list(population[i]))

            # Fill the rest via tournament selection + crossover + mutation
            current_mr = self.adaptive_mutation_rate(gen)
            while len(next_gen) < self.pop_size:
                p1 = self.tournament_select(population, fitnesses)
                p2 = self.tournament_select(population, fitnesses)
                c1, c2 = self.uniform_crossover(p1, p2)
                c1 = self.mutate(c1, current_mr)
                c2 = self.mutate(c2, current_mr)
                next_gen.append(c1)
                if len(next_gen) < self.pop_size:
                    next_gen.append(c2)

            population = next_gen

        return history


# ──────────────────────────────────────────────
# RANDOM BASELINE (for comparison)
# ──────────────────────────────────────────────
def random_recommendations(user_id: int, count: int = 6) -> list:
    """Generate random product recommendations as a baseline."""
    chosen = random.sample(products_list, count)
    ga_temp = HybridGeneticAlgorithm(user_id)
    score = ga_temp.fitness(chosen)
    return {
        "score": round(score, 2),
        "products": [
            {
                "id": pid,
                "category": product_dict[pid]["category"],
                "price": product_dict[pid]["price"],
            }
            for pid in chosen
        ],
    }


# ──────────────────────────────────────────────
# API ENDPOINTS
# ──────────────────────────────────────────────
@app.get("/users")
def get_users():
    """Return all users."""
    return df_users.to_dict(orient="records")


@app.get("/users/{user_id}/profile")
def get_user_profile(user_id: int):
    """Return detailed analytics for a specific user."""
    if user_id not in df_users["user_id"].values:
        raise HTTPException(status_code=404, detail="User not found")

    user_row = df_users[df_users["user_id"] == user_id].iloc[0]
    cat_prefs, purchased, avg_price, _ = get_user_preferences(user_id)

    # Top rated products
    u_ratings = df_ratings[df_ratings["user_id"] == user_id].sort_values("rating", ascending=False).head(5)
    top_rated = []
    for _, r in u_ratings.iterrows():
        pid = int(r["product_id"])
        if pid in product_dict:
            top_rated.append({
                "id": pid,
                "category": product_dict[pid]["category"],
                "price": product_dict[pid]["price"],
                "rating": int(r["rating"]),
            })

    # Behavior summary
    u_beh = df_behavior[df_behavior["user_id"] == user_id]
    total_views = int(u_beh["viewed"].sum())
    total_clicks = int(u_beh["clicked"].sum())
    total_purchases = int(u_beh["purchased"].sum())

    return {
        "user_id": user_id,
        "age": int(user_row["age"]),
        "country": str(user_row["country"]),
        "category_preferences": {k: int(v) for k, v in cat_prefs.items()},
        "total_purchases": len(purchased),
        "avg_price": float(round(avg_price, 2)),
        "total_views": total_views,
        "total_clicks": total_clicks,
        "total_purchase_events": total_purchases,
        "top_rated_products": top_rated,
    }


@app.get("/recommend/{user_id}")
def recommend(user_id: int):
    """Run the Hybrid GA and return full evolution history."""
    if user_id not in df_users["user_id"].values:
        raise HTTPException(status_code=404, detail="User not found")

    ga = HybridGeneticAlgorithm(user_id=user_id)
    history = ga.run()

    return {
        "user_id": user_id,
        "algorithm": "Hybrid GA + Collaborative Filtering",
        "params": {
            "population_size": ga.pop_size,
            "chromosome_length": ga.chromosome_length,
            "generations": ga.generations,
            "tournament_size": ga.tournament_size,
            "elite_count": ga.elite_count,
            "initial_mutation_rate": ga.initial_mutation_rate,
            "final_mutation_rate": ga.final_mutation_rate,
        },
        "history": history,
        "final_recommendations": history[-1]["recommendations"],
    }


@app.get("/recommend/{user_id}/compare")
def compare(user_id: int):
    """Compare GA recommendations vs random baseline."""
    if user_id not in df_users["user_id"].values:
        raise HTTPException(status_code=404, detail="User not found")

    ga = HybridGeneticAlgorithm(user_id=user_id)
    history = ga.run()
    ga_result = {
        "score": history[-1]["best_score"],
        "products": history[-1]["recommendations"],
    }
    rand_result = random_recommendations(user_id, count=ga.chromosome_length)

    improvement = 0
    if rand_result["score"] != 0:
        improvement = round(((ga_result["score"] - rand_result["score"]) / abs(rand_result["score"])) * 100, 1)

    return {
        "user_id": user_id,
        "ga": ga_result,
        "random": rand_result,
        "improvement_percent": improvement,
    }


@app.get("/stats")
def global_stats():
    """Return global dataset statistics."""
    cat_counts = df_products["category"].value_counts().to_dict()
    country_counts = df_users["country"].value_counts().to_dict()
    avg_rating = round(float(df_ratings["rating"].mean()), 2)

    top_products_by_popularity = sorted(product_popularity.items(), key=lambda x: x[1], reverse=True)[:10]
    top_products = [
        {
            "id": pid,
            "category": product_dict[pid]["category"],
            "price": product_dict[pid]["price"],
            "popularity_score": round(score, 2),
        }
        for pid, score in top_products_by_popularity
    ]

    return {
        "total_users": len(df_users),
        "total_products": len(df_products),
        "total_ratings": len(df_ratings),
        "total_behavior_records": len(df_behavior),
        "avg_rating": avg_rating,
        "categories": cat_counts,
        "countries": country_counts,
        "top_products": top_products,
    }


# Serve frontend static files
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
