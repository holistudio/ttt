```bash
# create env
conda create -n ttt python=3.11
conda activate ttt

# install uv inside the env
conda install -c conda-forge uv

# install backend deps with uv
uv pip install -r requirements.txt

# run server
# cd backend # if not already
python app.py
```
