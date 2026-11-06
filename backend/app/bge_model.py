"""#124 공유 DB와 질문 임베딩이 함께 지켜야 하는 모델 계약."""
MODEL = 'BAAI/bge-m3'
DIMENSIONS = 1024
REVISION = '5617a9f61b028005a4858fdac845db406aefb181'
WEIGHTS_SHA256 = 'b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38'
PROVENANCE = {'model_revision': REVISION, 'weights_sha256': WEIGHTS_SHA256,
              'pooling': 'CLS', 'normalization': 'L2'}
