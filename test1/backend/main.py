import pandas as pd
import numpy as np
import random
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI(title="GA Recommender System API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load data
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_new")

try:
    df_users = pd.read_excel(os.path.join(DATA_DIR, "users.xlsx"))
    df_products = pd.read_excel(os.path.join(DATA_DIR, "products.xlsx"))
    df_ratings = pd.read_excel(os.path.join(DATA_DIR, "ratings.xlsx"))
    df_behavior = pd.read_excel(os.path.join(DATA_DIR, "behavior_15500.xlsx"))
    
    # Precompute global product scores
    product_scores = {}
    for _, row in df_products.iterrows():
        pid = row['product_id']
        # Global popularity based on behavior
        b_data = df_behavior[df_behavior['product_id'] == pid]
        score = b_data['viewed'].sum() * 1 + b_data['clicked'].sum() * 3 + b_data['purchased'].sum() * 10
        # Global average rating
        r_data = df_ratings[df_ratings['product_id'] == pid]
        if len(r_data) > 0:
            score += r_data['rating'].mean() * 5
        product_scores[pid] = score

    products_list = df_products['product_id'].tolist()
    product_dict = df_products.set_index('product_id').to_dict('index')
    
except Exception as e:
    print(f"Error loading data: {e}")

def get_user_preferences(user_id):
    prefs = {}
    purchased = set()
    
    # Analyze behavior
    u_behavior = df_behavior[df_behavior['user_id'] == user_id]
    for _, row in u_behavior.iterrows():
        pid = row['product_id']
        cat = product_dict[pid]['category']
        weight = row['viewed'] * 1 + row['clicked'] * 3 + row['purchased'] * 10
        prefs[cat] = prefs.get(cat, 0) + weight
        if row['purchased'] > 0:
            purchased.add(pid)
            
    # Analyze ratings
    u_ratings = df_ratings[df_ratings['user_id'] == user_id]
    for _, row in u_ratings.iterrows():
        pid = row['product_id']
        cat = product_dict[pid]['category']
        prefs[cat] = prefs.get(cat, 0) + row['rating'] * 2
        
    return prefs, purchased

class GeneticAlgorithm:
    def __init__(self, user_id, pop_size=20, chromosome_length=5, generations=15, mutation_rate=0.1):
        self.user_id = user_id
        self.pop_size = pop_size
        self.chromosome_length = chromosome_length
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.user_prefs, self.user_purchased = get_user_preferences(user_id)
        
    def fitness(self, chromosome):
        score = 0
        categories = set()
        for pid in chromosome:
            # 1. User category preference
            cat = product_dict[pid]['category']
            score += self.user_prefs.get(cat, 0)
            
            # 2. Global product score
            score += product_scores.get(pid, 0) * 0.1 # Weight it down compared to personal pref
            
            # 3. Penalty for already purchased
            if pid in self.user_purchased:
                score -= 1000
                
            categories.add(cat)
            
        # 4. Diversity bonus
        score += len(categories) * 50
        
        # 5. Uniqueness in chromosome penalty (don't recommend same product twice)
        if len(set(chromosome)) < len(chromosome):
            score -= 2000
            
        return score

    def create_individual(self):
        return random.sample(products_list, self.chromosome_length)

    def crossover(self, parent1, parent2):
        cut = random.randint(1, self.chromosome_length - 1)
        child1 = parent1[:cut] + parent2[cut:]
        child2 = parent2[:cut] + parent1[cut:]
        return child1, child2

    def mutate(self, chromosome):
        if random.random() < self.mutation_rate:
            idx = random.randint(0, self.chromosome_length - 1)
            chromosome[idx] = random.choice(products_list)
        return chromosome

    def run(self):
        population = [self.create_individual() for _ in range(self.pop_size)]
        history = []
        
        for gen in range(self.generations):
            # Evaluate fitness
            pop_fitness = [(ind, self.fitness(ind)) for ind in population]
            pop_fitness.sort(key=lambda x: x[1], reverse=True)
            
            best_ind, best_score = pop_fitness[0]
            
            # Record history
            best_products = [
                {
                    "id": pid, 
                    "category": product_dict[pid]['category'], 
                    "price": product_dict[pid]['price']
                } for pid in best_ind
            ]
            history.append({
                "generation": gen + 1,
                "best_score": round(best_score, 2),
                "recommendations": best_products
            })
            
            # Selection (top 50%)
            survivors = [ind for ind, score in pop_fitness[:self.pop_size // 2]]
            
            # Crossover & Mutation to fill next generation
            next_gen = survivors.copy()
            while len(next_gen) < self.pop_size:
                p1, p2 = random.sample(survivors, 2)
                c1, c2 = self.crossover(p1, p2)
                next_gen.append(self.mutate(c1))
                if len(next_gen) < self.pop_size:
                    next_gen.append(self.mutate(c2))
                    
            population = next_gen
            
        return history

@app.get("/users")
def get_users():
    return df_users.to_dict(orient="records")

@app.get("/recommend/{user_id}")
def recommend(user_id: int):
    if user_id not in df_users['user_id'].values:
        raise HTTPException(status_code=404, detail="User not found")
        
    ga = GeneticAlgorithm(user_id=user_id)
    history = ga.run()
    
    return {
        "user_id": user_id,
        "history": history,
        "final_recommendations": history[-1]['recommendations']
    }
