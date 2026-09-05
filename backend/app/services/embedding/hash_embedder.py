import hashlib
import numpy as np
from typing import Sequence
from .base import BaseEmbedder

class HashEmbedder(BaseEmbedder):
    name = "hash"
    model_id = "local/hash-384"

    @property
    def dim(self) -> int:
        return 384

    def _embed_text(self, text: str) -> np.ndarray:
        tokens = text.split()
        if not tokens:
            return np.zeros(self.dim, dtype=np.float32)
        
        vector = np.zeros(self.dim, dtype=np.float32)
        for token in tokens:
            for d in range(self.dim):
                h = hashlib.md5(f"{token}_{d}".encode('utf-8')).digest()
                val = int.from_bytes(h[:4], byteorder='big') / 4294967295.0 * 2.0 - 1.0
                vector[d] += val
                
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        return vector

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        vectors = [self._embed_text(t) for t in texts]
        return np.array(vectors, dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed_text(text)
