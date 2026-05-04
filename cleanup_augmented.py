import os
import re


def remove_orphan_augmented_images(dataset_dir='dish_dataset_clean'):
    """
    Usuwa zdjęcia z train/augmented, które nie mają odpowiadającego numeru w train/raw.

    Przykład dopasowania:
    - raw: 12_raw.jpg -> numer 12
    - augmented: 12_v0.jpg -> numer 12
    """
    raw_pattern = re.compile(r'^(\d+)_raw\.jpg$', re.IGNORECASE)
    aug_pattern = re.compile(r'^(\d+)_v\d+\.jpg$', re.IGNORECASE)

    removed_count = 0

    for dish_name in os.listdir(dataset_dir):
        dish_dir = os.path.join(dataset_dir, dish_name)
        if not os.path.isdir(dish_dir):
            continue

        train_raw_dir = os.path.join(dish_dir, 'train', 'raw')
        train_aug_dir = os.path.join(dish_dir, 'train', 'augmented')

        if not os.path.isdir(train_raw_dir) or not os.path.isdir(train_aug_dir):
            continue

        raw_numbers = set()
        for fname in os.listdir(train_raw_dir):
            match = raw_pattern.match(fname)
            if match:
                raw_numbers.add(match.group(1))

        for fname in os.listdir(train_aug_dir):
            match = aug_pattern.match(fname)
            if not match:
                continue

            aug_number = match.group(1)
            if aug_number not in raw_numbers:
                os.remove(os.path.join(train_aug_dir, fname))
                removed_count += 1

    return removed_count


if __name__ == '__main__':
    removed = remove_orphan_augmented_images()
    print('Usunięto {} osieroconych zdjęć z train/augmented.'.format(removed))