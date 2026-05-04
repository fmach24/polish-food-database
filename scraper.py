# ================================================================
# KROK 1: Instalacja bibliotek
# pip install -q pillow numpy tqdm requests
# ================================================================

# ================================================================
# KROK 2: Importy
# ================================================================
import os
import re
import random
import shutil
import requests
import warnings
import numpy as np
import argparse
import hashlib
import imagehash
from io import BytesIO
from tqdm import tqdm
from PIL import Image, ImageOps, ImageEnhance

warnings.filterwarnings('ignore')

# ================================================================
# KROK 3: Ustawienia
# ================================================================

# Lista potraw do pobrania
MY_DISHES = [
    'Kotlet Schabowy',
    'Pierogi Ruskie',
    'Rosol',
    'Placki ziemniaczane',
    'Zurek',
    'Pomidorowa',
    'Oscypek',
    'Zupa ziemniaczana',
    'Pierogi z owocami',
    'Bigos'
]

LIMIT    = 300   # ile URL pobieramy z Binga na potrawę
VARIANTS = 3     # ile augmentowanych kopii na jedno zdjęcie

# Katalogi
DATASET_DIR = 'dish_dataset_clean'   # tu zapisywany jest dataset
TRAIN_VAL_SPLIT = 0.75  # proporcja treningowy/walidacyjny
SPLIT_SEED = 42  # dla powtarzalności
PHASH_THRESHOLD = 10  # próg podobieństwa obrazów (0=identyczne, 64=zupełnie inne)

# Custom warianty zapytań dla każdej potrawy (możesz edytować!)
QUERY_VARIANTS = {
    'Kotlet Schabowy': ['kotlet schabowy'], # TODO DODAC WIĘCEJ WARIANTÓW BO MALO
    'Pierogi Ruskie': ['pierogi ruskie'],   # TODO DODAC WIĘCEJ WARIANTÓW BO MALO
    'Rosol': ['rosół', 'rosol'],
    'Placki ziemniaczane': ['placki ziemniaczane', 'placki kartoflane'],
    'Zurek': ['żurek', 'żurku', 'żur', 'zupa żurek'],
    'Pomidorowa': ['zupa pomidorowa', 'pomidorowa', 'tomato soup', 'zupa pomidorowa z ziemniakami'],
    'Oscypek': ['oscypek', 'oscypki'],
    'Zupa ziemniaczana': ['zupa ziemniaczana', 'zupa kartoflana', 'potato soup'],
    'Pierogi z owocami': ['pierogi z owocami', 'pierogi słodkie', 'sweet pierogi', 'pierogi z jagodami'],
    #TODO zmienic nazwe na SLODKIE PIEROGI
    'Bigos': ['bigos', 'bigos myśliwski'],
}

#TODO usunac augmentowane nieuzywane 
#TODO baerdziej przefiltrować z vaild pod katem powtorek, bo na pewno są
#TODO pousuwac zdj z tej kategori


# ================================================================
# KROK 4: Wszystkie funkcje pomocnicze
# ================================================================

# ---------- AUGMENTACJA ----------

def add_salt_and_pepper(img, amount=0.02):
    pixels = np.array(img)
    num_salt   = int(np.ceil(amount * pixels.size * 0.5))
    num_pepper = int(np.ceil(amount * pixels.size * 0.5))
    for _ in range(num_salt):
        r = np.random.randint(0, pixels.shape[0] - 1)
        c = np.random.randint(0, pixels.shape[1] - 1)
        pixels[r, c] = [255, 255, 255]
    for _ in range(num_pepper):
        r = np.random.randint(0, pixels.shape[0] - 1)
        c = np.random.randint(0, pixels.shape[1] - 1)
        pixels[r, c] = [0, 0, 0]
    return Image.fromarray(pixels)

def augment_image(img, output_size=(512, 512)):
    img = img.rotate(random.randint(0, 360), expand=True, fillcolor=(255, 255, 255))
    if random.random() > 0.5:
        img = ImageOps.mirror(img)
    img = ImageEnhance.Brightness(img).enhance(random.uniform(0.7, 1.3))
    if random.random() > 0.4:
        img = add_salt_and_pepper(img, amount=random.uniform(0.01, 0.04))
    img.thumbnail(output_size, Image.Resampling.LANCZOS)
    final_img = Image.new('RGB', output_size, (255, 255, 255))
    offset = ((output_size[0] - img.size[0]) // 2, (output_size[1] - img.size[1]) // 2)
    final_img.paste(img, offset)
    return final_img

# ---------- POBIERANIE ----------

def get_bing_urls(query, limit):
    """Pobiera URL zdjęć z wielu stron Binga."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}
    all_urls = []
    
    # Pobierz z 4 stron (każda strona ma ~35 wyników, razem ~140)
    for page in range(1, 5):
        try:
            first = 1 + (page - 1) * 35
            url = 'https://www.bing.com/images/search?q=' + query.replace(' ', '+') + '&first={}'.format(first)
            res = requests.get(url, headers=headers, timeout=10)
            urls = re.findall(r'murl&quot;:&quot;(http.*?)&quot;', res.text)
            all_urls.extend(urls)
            if len(all_urls) >= limit:
                break
        except Exception:
            continue
    
    return all_urls[:limit]

def get_bing_urls_multi(query, limit=300):
    """
    Pobiera URL'e z wielu wariantów zapytania.
    Używa custom wariantów z QUERY_VARIANTS jeśli dostępne, inaczej generuje automatyczne.
    """
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}
    all_urls_set = set()  # do deduplikacji
    
    # Sprawdź czy są custom warianty dla tej potrawy
    if query in QUERY_VARIANTS:
        query_variants = QUERY_VARIANTS[query]
        print('  Szukam wariantów: {}'.format(', '.join(query_variants[:5])) + ('...' if len(query_variants) > 5 else ''))
    else:
        # Generuj warianty automatycznie
        query_lower = query.lower()
        query_variants = [
            query,                          # oryginalny
            query_lower,                    # małe litery
        ]
        
        print('  Szukam wariantów (auto): {}'.format(', '.join(query_variants)))
    
    # Pobierz URL'e dla każdego wariantu
    for variant in query_variants:
        for page in range(1, 5):
            try:
                first = 1 + (page - 1) * 35
                url = 'https://www.bing.com/images/search?q=' + variant.replace(' ', '+') + '&first={}'.format(first)
                res = requests.get(url, headers=headers, timeout=10)
                urls = re.findall(r'murl&quot;:&quot;(http.*?)&quot;', res.text)
                all_urls_set.update(urls)  # dodaj do zbioru (auto-deduplikacja)
                if len(all_urls_set) >= limit:
                    break
            except Exception:
                continue
        
        if len(all_urls_set) >= limit:
            break
    
    return list(all_urls_set)[:limit]

# ---------- SPRAWDZANIE DUPLIKATÓW ----------

def get_phash(file_path):
    """Oblicza perceptual hash (pHash) zdjęcia."""
    try:
        return imagehash.phash(Image.open(file_path))
    except Exception:
        return None

def is_duplicate_phash(new_hash, existing_hashes):
    """Sprawdza czy zdjęcie jest podobne do któregoś z istniejących (wizualnie)."""
    if not new_hash:
        return False
    return any((new_hash - h) <= PHASH_THRESHOLD for h in existing_hashes)

def collect_existing_hashes(dataset_dir):
    """Zbiera pHash'e wszystkich zdjęć w istniejącym datasecie."""
    existing_hashes = []
    for root, _, files in os.walk(dataset_dir):
        for fname in files:
            if fname.endswith('.jpg'):
                path = os.path.join(root, fname)
                h = get_phash(path)
                if h:
                    existing_hashes.append(h)
    return existing_hashes

# ---------- PODZIAŁ I AUGMENTACJA ----------

def split_and_augment(raw_dir, train_raw_dir, train_aug_dir, val_raw_dir, variants=2):
    """
    Dzieli surowe zdjęcia 75/25 (treningowy/walidacyjny).
    Treningowe: augnentuje do variants kopii.
    Walidacyjne: zostawia bez augmentacji.
    """
    os.makedirs(train_raw_dir, exist_ok=True)
    os.makedirs(train_aug_dir, exist_ok=True)
    os.makedirs(val_raw_dir, exist_ok=True)
    
    # Lista wszystkich pobranych zdjęć
    raw_files = [f for f in os.listdir(raw_dir) if f.endswith('.jpg')]
    if not raw_files:
        return 0, 0
    
    # Losowy podział 75/25
    random.seed(SPLIT_SEED)
    random.shuffle(raw_files)
    split_idx = int(len(raw_files) * TRAIN_VAL_SPLIT)
    train_files = raw_files[:split_idx]
    val_files = raw_files[split_idx:]
    
    # Przenieś walidacyjne do val/raw
    for i, fname in enumerate(val_files):
        src = os.path.join(raw_dir, fname)
        dst = os.path.join(val_raw_dir, '{}_val.jpg'.format(i))
        shutil.copy2(src, dst)
    
    # Przenieś treningowe do train/raw i zrób augmentację
    for i, fname in enumerate(train_files):
        src = os.path.join(raw_dir, fname)
        dst = os.path.join(train_raw_dir, '{}_raw.jpg'.format(i))
        shutil.copy2(src, dst)
        
        # Augmentuj
        img = Image.open(src).convert('RGB')
        for v in range(variants):
            aug = augment_image(img)
            aug.save(os.path.join(train_aug_dir, '{}_v{}.jpg'.format(i, v)), 'JPEG')
    
    return len(train_files), len(val_files)


def add_single_dish(dish_name, limit=LIMIT, variants=VARIANTS):
    """
    Dodaje jedną potrawę do istniejącego datasetu.
    Sprawdza duplikaty i dodaje tylko nowe zdjęcia.
    """
    print('\n=== DODAWANIE NOWEJ POTRAWY ===')
    print('Potrawa: {}'.format(dish_name))
    
    # Zbierz hashe wszystkich istniejących zdjęć w datasecie
    print('Skanowanie istniejących zdj\u0119\u0107...')
    existing_hashes = collect_existing_hashes(DATASET_DIR)
    print('Znaleziono {} istniejących zdj\u0119\u0107'.format(len(existing_hashes)))
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    folder = dish_name.replace(' ', '_')
    temp_raw_dir = os.path.join(DATASET_DIR, folder, '.temp_raw')
    train_raw_dir = os.path.join(DATASET_DIR, folder, 'train', 'raw')
    train_aug_dir = os.path.join(DATASET_DIR, folder, 'train', 'augmented')
    val_raw_dir = os.path.join(DATASET_DIR, folder, 'val', 'raw')
    os.makedirs(temp_raw_dir, exist_ok=True)
    
    # Pobierz URL'e
    urls = get_bing_urls_multi(dish_name, limit)
    if not urls:
        print('UWAGA: brak URL dla {}'.format(dish_name))
        return
    
    print('\nPobieranie i sprawdzanie duplikat\u00f3w...')
    count = 0
    duplicates = 0
    
    for url in tqdm(urls, desc=dish_name):
        try:
            res = requests.get(url, headers=headers, timeout=5)
            img = Image.open(BytesIO(res.content)).convert('RGB')
            
            # Zapisz tymczasowo
            temp_path = os.path.join(temp_raw_dir, '{}.jpg'.format(count))
            img.save(temp_path, 'JPEG')
            
            # Sprawdź duplikat (perceptual hash)
            file_hash = get_phash(temp_path)
            if is_duplicate_phash(file_hash, existing_hashes):
                duplicates += 1
                os.remove(temp_path)
            else:
                if file_hash:
                    existing_hashes.append(file_hash)
                count += 1
        except Exception:
            continue
    
    # Podziel na train/val i augmentuj
    if count == 0:
        print('Brak nowych zdj\u0119\u0107 (wszystkie s\u0105 duplikatami).')
        if os.path.exists(temp_raw_dir):
            shutil.rmtree(temp_raw_dir)
        return
    
    n_train, n_val = split_and_augment(temp_raw_dir, train_raw_dir, train_aug_dir, val_raw_dir, variants)
    
    # Usu\u0144 tymczasowy katalog
    if os.path.exists(temp_raw_dir):
        shutil.rmtree(temp_raw_dir)
    
    print('\n--- Podsumowanie dodawania ---')
    print('Pobranych: {}'.format(count + duplicates))
    print('Duplikat\u00f3w: {}'.format(duplicates))
    print('Nowych: {}'.format(count))
    print('Treningowych: {} + {} augmentacji'.format(n_train, n_train * variants))
    print('Walidacyjnych: {} (bez augmentacji)'.format(n_val))
    print('Razem nowych zdj\u0119\u0107 w zbiorze: {}'.format(n_train + n_val + n_train * variants))


# ================================================================
# KROK 5: Pobieranie datasetu
# Struktura zapisu:
#   dish_dataset_clean/
#       Kotlet_Schabowy/
#           train/
#               raw/        <-- 75% oryginalnych zdjęć
#               augmented/  <-- augmentowane kopie (2x więcej niż raw)
#           val/
#               raw/        <-- 25% oryginalnych zdjęć (bez augmentacji)
# ================================================================

def build_dataset(dish_list, limit=100, variants=2):
    headers = {'User-Agent': 'Mozilla/5.0'}

    total_raw = 0
    total_aug = 0

    for dish in dish_list:
        print('\n Potrawa: {}'.format(dish))

        folder = dish.replace(' ', '_')
        temp_raw_dir = os.path.join(DATASET_DIR, folder, '.temp_raw')
        train_raw_dir = os.path.join(DATASET_DIR, folder, 'train', 'raw')
        train_aug_dir = os.path.join(DATASET_DIR, folder, 'train', 'augmented')
        val_raw_dir = os.path.join(DATASET_DIR, folder, 'val', 'raw')
        os.makedirs(temp_raw_dir, exist_ok=True)

        # Zbierz pHash'e istniejących zdjęć dla tej potrawy
        existing_hashes = []
        for dirs in [train_raw_dir, train_aug_dir, val_raw_dir]:
            if os.path.isdir(dirs):
                for fname in os.listdir(dirs):
                    if fname.endswith('.jpg'):
                        path = os.path.join(dirs, fname)
                        h = get_phash(path)
                        if h:
                            existing_hashes.append(h)

        urls = get_bing_urls_multi(dish, limit)
        if not urls:
            print('  UWAGA: brak URL dla {}'.format(dish))
            continue

        count = 0
        duplicates = 0
        for url in tqdm(urls, desc=dish):
            try:
                res = requests.get(url, headers=headers, timeout=5)
                img = Image.open(BytesIO(res.content)).convert('RGB')
                temp_path = os.path.join(temp_raw_dir, '{}.jpg'.format(count))
                img.save(temp_path, 'JPEG')
                
                # Sprawdź duplikat (perceptual hash)
                file_hash = get_phash(temp_path)
                if is_duplicate_phash(file_hash, existing_hashes):
                    duplicates += 1
                    os.remove(temp_path)
                else:
                    if file_hash:
                        existing_hashes.append(file_hash)
                    count += 1
            except Exception:
                continue

        if count == 0:
            print('  Brak nowych zdjęć (wszystkie są duplikatami).')
            if os.path.exists(temp_raw_dir):
                shutil.rmtree(temp_raw_dir)
            continue

        # Teraz podziel na train/val i zrób augmentację tylko na train
        n_train, n_val = split_and_augment(temp_raw_dir, train_raw_dir, train_aug_dir, val_raw_dir, variants)
        
        # Usuń tymczasowy katalog
        if os.path.exists(temp_raw_dir):
            shutil.rmtree(temp_raw_dir)
        
        print('  Pobranych: {}'.format(count + duplicates))
        print('  Duplikatów: {}'.format(duplicates))
        print('  Nowych: {}'.format(count))
        print('  Treningowych: {} + {} augmentacji'.format(n_train, n_train * variants))
        print('  Walidacyjnych: {} (bez augmentacji)'.format(n_val))

        total_raw += n_train + n_val
        total_aug += n_train * variants

    print('\n==============================')
    print('GOTOWE')
    print('Oryginalow lacznie:    {}'.format(total_raw))
    print('Augmentowanych lacznie:{}'.format(total_aug))
    print('==============================')


# ▶▶▶ MAIN - Obsługa argumentów
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Scraper polskich dań do datasetu')
    parser.add_argument('--add', type=str, help='Dodaj jedną potrawę do istniejącego datasetu (np. --add "Nazwa Potrawy")')
    parser.add_argument('--limit', type=int, default=LIMIT, help='Liczba URL do pobrania (default: {})'.format(LIMIT))
    parser.add_argument('--variants', type=int, default=VARIANTS, help='Liczba augmentacji (default: {})'.format(VARIANTS))
    
    args = parser.parse_args()
    
    if args.add:
        # Tryb dodawania jednej potrawy
        add_single_dish(args.add, limit=args.limit, variants=args.variants)
    else:
        # Tryb budowania całego datasetu
        build_dataset(MY_DISHES, limit=args.limit, variants=args.variants)
    
    # Podsumowanie datasetu
    print('\n' + '='*62)
    print('{:<25} {:>10} {:>15} {:>12}'.format('Klasa', 'Train', 'Augm+', 'Val'))
    print('-' * 62)
    
    total_train = 0
    total_train_aug = 0
    total_val = 0
    
    for folder in sorted(os.listdir(DATASET_DIR)):
        if folder.startswith('.'):
            continue
        train_raw_dir = os.path.join(DATASET_DIR, folder, 'train', 'raw')
        train_aug_dir = os.path.join(DATASET_DIR, folder, 'train', 'augmented')
        val_raw_dir = os.path.join(DATASET_DIR, folder, 'val', 'raw')
    
        n_train = len([f for f in os.listdir(train_raw_dir) if f.endswith('.jpg')]) if os.path.isdir(train_raw_dir) else 0
        n_aug = len([f for f in os.listdir(train_aug_dir) if f.endswith('.jpg')]) if os.path.isdir(train_aug_dir) else 0
        n_val = len([f for f in os.listdir(val_raw_dir) if f.endswith('.jpg')]) if os.path.isdir(val_raw_dir) else 0
    
        print('{:<25} {:>10} {:>15} {:>12}'.format(folder, n_train, n_aug, n_val))
        total_train += n_train
        total_train_aug += n_aug
        total_val += n_val
    
    print('-' * 62)
    print('{:<25} {:>10} {:>15} {:>12}'.format('RAZEM', total_train, total_train_aug, total_val))
    print('='*62)


