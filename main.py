# ==========================
# Medical Chatbot Backend (AutoGen + OpenAI API + RAG)
# ==========================

import os
from dotenv import load_dotenv
from datasets import load_dataset
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import autogen_agentchat  # Use autogen_agentchat instead of autogen
import autogen_ext  # Use autogen_ext for OpenAI API support
import gc # Garbage collection

# ==========================
# Step 1: Load OpenAI API Key
# ==========================
load_dotenv()  # Load environment variables from .env file
openai_api_key = os.getenv("OPENAI_API_KEY")
# Check for OpenAI API key exist
if not openai_api_key:
    raise ValueError("❌ OpenAI API key is missing! Add it to .env file or environment variables.")

# ==========================
# Step 2: Load the Medical Dataset from Hugging Face
# ==========================
print("✅ Loading medical dataset...")
dataset = load_dataset("ruslanmv/ai-medical-chatbot")
# Extract patient-doctor conversations
# medical_dialogues = dataset["train"].to_pandas()[["Patient", "Doctor"]]
medical_dialogues = dataset["train"].to_pandas()[["Patient", "Doctor"]].head(10000)  # Use first 10,000 rows to reduce RAM usage
# Extract patient-doctor conversations
print(f"✅ Loaded {len(medical_dialogues)} medical Q&A pairs.")

# ==========================
# Step 3: Convert Dataset into FAISS Embeddings
# ==========================
print("✅ Generating FAISS vector embeddings...")
# Load sentence transformer model
# embedding_model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
embedding_model = SentenceTransformer("sentence-transformers/paraphrase-MiniLM-L3-v2", device="cpu") # Smaller model for less usage of RAM
# Convert text into embeddings
medical_qa = [
    {"question": row["Patient"], "answer": row["Doctor"]}
    for _, row in medical_dialogues.iterrows()
]
# Generate vector embeddings
medical_embeddings = embedding_model.encode(
    [qa["question"] + " " + qa["answer"] for qa in medical_qa], 
    convert_to_numpy=True
) # Embedding with float64
medical_embeddings = np.array(medical_embeddings, dtype=np.float32) # Re-embedding with float32
faiss_index_path = "data/medical_faiss_index"
# Save FAISS index only if it doesn’t exist, this prevents corrupt FAISS indices from causing a crash.
if not os.path.exists(faiss_index_path):
    print("✅ Creating FAISS index...")
    # Create FAISS index
    # index = faiss.IndexFlatL2(medical_embeddings.shape[1])
    index = faiss.IndexHNSWFlat(medical_embeddings.shape[1], 32)  # 32 = HNSW graph connections
    index.add(medical_embeddings)
    faiss.write_index(index, faiss_index_path)
    # Manually free up memory
    del medical_embeddings
    gc.collect()
    print("✅ Memory cleared after FAISS indexing.")
else:
    print("✅ Loading existing FAISS index...")
print("✅ FAISS index saved successfully!")

# ==========================
# Step 4: Retrieval-Augmented Generation (RAG) Implementation
# ==========================
print("✅ Initializing RAG-based medical chatbot...")
# Load FAISS index for retrieval
index = faiss.read_index(faiss_index_path)
# Retrieve medical KB using FAISS
def retrieve_medical_info(query):
    """Retrieve relevant medical knowledge using FAISS"""
    query_embedding = embedding_model.encode([query], convert_to_numpy=True)
    _, idxs = index.search(query_embedding, k=3)  # Get top 3 matches
    return [medical_qa[i]["answer"] for i in idxs[0]]

# ==========================
# Step 5: AutoGen AI Chatbot Implementation
# ==========================
# class MedicalChatbot(autogen_agentchat.AssistantAgent): # assistant-type agents
class MedicalChatbot(autogen_agentchat.ChatAgent):        # chat-type agents
    def generate_reply(self, messages):
        """Handles medical queries using RAG + OpenAI API"""
        query = messages[-1]["content"]  # Get latest user query
        retrieved_info = retrieve_medical_info(query)
        knowledge_base = "\n".join(retrieved_info)
        # Create enhanced response prompt
        prompt = (
            f"Using the following medical knowledge:\n{knowledge_base}\n"
            f"Answer the question in a professional and medically accurate manner: {query}"
        )
        return self.llm.complete(prompt)
# Instantiate the chatbot with OpenAI GPT-4
chatbot = MedicalChatbot(
    name="Medical_Chatbot",
    llm_config={
        "model": "gpt-4", 
        "api_key": openai_api_key
    }
)
print("✅ Medical chatbot is ready!")

# ==========================
# Step 6: Interactive Chat Testing (For Local Debugging)
# ==========================
if __name__ == "__main__":
    print("\n🩺 Medical Chatbot is running...\n")
    # Start session
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["exit", "quit"]:
            print("👋 Chatbot session ended.")
            break
        # Prepare JSON reply response body
        response = chatbot.generate_reply([{"role": "user", "content": user_input}])
        print("Chatbot:", response)
