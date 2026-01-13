import pandas as pd
import pickle
from sklearn.model_selection import train_test_split
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import accuracy_score, classification_report
from sentence_transformers import SentenceTransformer
import numpy as np

def train_model():
    print("📂 Loading dataset...")

    # Load CSV
    df = pd.read_csv('consumer_complaints.csv')

    # Clean data
    df = df.dropna(subset=['complaint_text', 'product']).drop_duplicates()
    df['complaint_text'] = df['complaint_text'].str.strip()
    df['product'] = df['product'].str.strip()

    print(f"✅ Dataset loaded with {len(df)} rows and {df['product'].nunique()} categories.")

    X = df['complaint_text'].astype(str)
    y = df['product']

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Load multilingual embedding model
    print("🔍 Loading embedding model...")
    emb_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    # Encode text
    print("⚙️ Encoding training & testing data...")
    X_train_embeddings = emb_model.encode(X_train.tolist())
    X_test_embeddings = emb_model.encode(X_test.tolist())

    # ✅ Use SGDClassifier for incremental learning
    print("📊 Training SGDClassifier with incremental learning support...")
    classes = np.unique(y)
    model = SGDClassifier(loss="log_loss", max_iter=1000, tol=1e-3)
    model.partial_fit(X_train_embeddings, y_train, classes=classes)

    # Evaluate
    y_pred = model.predict(X_test_embeddings)
    print(f"🎯 Accuracy: {accuracy_score(y_test, y_pred):.3f}")
    print("\n📄 Classification Report:")
    print(classification_report(y_test, y_pred))

    # Save model & embedding model
    with open('complaint_model.pkl', 'wb') as f:
        pickle.dump(model, f)

    emb_model.save("embedding_model")

    # Save classes for future incremental updates in app.py
    with open('classes.pkl', 'wb') as f:
        pickle.dump(classes, f)

    print("✅ Model, embedding model, and classes saved successfully!")

if __name__ == "__main__":
    train_model()
