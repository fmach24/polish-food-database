# polish-food-database

## Struktura datasetu

Ten projekt buduje dataset w katalogu `dish_dataset_clean/`. Każda potrawa ma własny folder, a w nim podział na `train` i `val`.

Możesz skopiować poniższą strukturę i wkleić ją do chatbota, jeśli chcesz szybko wytłumaczyć, jak działa dataset:

```text
dish_dataset_clean/
	Kotlet_Schabowy/
		train/
			raw/
				0_raw.jpg
				1_raw.jpg
				2_raw.jpg
			augmented/
				0_v0.jpg
				0_v1.jpg
				0_v2.jpg
				1_v0.jpg
				1_v1.jpg
				1_v2.jpg
		val/
			raw/
				0_val.jpg
				1_val.jpg
	Pierogi_Ruskie/
		train/
			raw/
			augmented/
		val/
			raw/
```

Jak to działa:

- `train/raw/` - oryginalne zdjęcia używane do trenowania modelu.
- `train/augmented/` - sztucznie wygenerowane wersje tych samych zdjęć, z tym samym numerem bazowym.
- `val/raw/` - zdjęcia do walidacji, bez augmentacji.

Przykład numeracji:

- `5_raw.jpg` oznacza oryginalne zdjęcie nr 5.
- `5_v0.jpg`, `5_v1.jpg`, `5_v2.jpg` to augmentacje tego samego zdjęcia nr 5.

To znaczy, że jeśli usuniesz jedno zdjęcie źródłowe, możesz też łatwo usunąć wszystkie jego augmentacje po tym samym numerze.