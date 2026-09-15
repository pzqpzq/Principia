# Gemstones: A Model Suite for Multi-Faceted Scaling Laws [NeurIPS 2025]
A joint project by: Sean McLeish, John Kirchenbauer, David Yu Miller, Siddharth Singh, Abhinav Bhatele, Micah Goldblum, Ashwinee Panda and Tom Goldstein.

<p align="center">
<a target="_blank" href="https://arxiv.org/abs/2502.06857">
<img style="height:22pt" src="https://img.shields.io/badge/-Paper-B31B1B?style=flat&logo=arxiv">
<a target="_blank" href="https://mcleish7.github.io/gemstone-scaling-laws/">
<img style="height:22pt" src="https://img.shields.io/badge/-🌐%20Website-1E8BC3?style=flat">
<a target="_blank" href="https://huggingface.co/collections/tomg-group-umd/gemstone-models-679408ee3f19f1d4d00e8b10">
<img style="height:22pt" src="https://img.shields.io/badge/-🤗%20Models-red?style=flat"></a>
<a target="_blank" href="https://tinyurl.com/gemstones-colab">
<img style="height:22pt" src="https://img.shields.io/badge/-Colab-F9AB00?style=flat&logo=googlecolab&logoColor=white"></a>
<br>
</p>

## Citing Our Work
To cite our work, please use this bibtex.
```
@article{mcleish2024gemstones
    title={Gemstones: A Model Suite for Multi-Faceted Scaling Laws}, 
    author={Sean McLeish and John Kirchenbauer and David Yu Miller and Siddharth Singh and Abhinav Bhatele and Micah Goldblum and Ashwinee Panda and Tom Goldstein},
    journal={arXiv preprint arXiv:2502.06857},
    year={2025},
    url={https://arxiv.org/abs/2502.06857},
}
```

## Getting Started
We developed in Python 3.10.4, to install run:
```
git clone git@github.com:mcleish7/gemstone-scaling-laws
cd gemstone-scaling-laws
pip install .
```

## Training Data
All of our training runs were completed on [Frontier](https://www.olcf.ornl.gov/olcf-resources/compute-systems/frontier/) at the Oak Ridge National Laboratory. 
We train in two hour intervals over multiple nodes of AMD MI250X GPUs logging to wandb.
We extract data from wandb using [wandb_data_extraction.py](wandb_data_extraction.py), where we stich the two hour chunks back into complete runs. 
However, our wandb space is currently private so we provide the intermediate dataframe after our we process the models, this is close to raw form apart from the runs being grouped.

## Fitting Laws
We provide bash commands to run all code needed in [shells/fitting.sh](shells/fitting.sh). We also give the outputs in json from in the `./parameters` folders as this is a compute intensive process.

### Approach 1
We use [approach_1.py](plotters/approach_1.py) to fit approach 1 laws. This is a quick process so we also plot at the same time.

### Approach 3
We use [depth_width.py](depth_width.py) to fit approach 3 laws. We provide our outputs in [parameters/](parameters/), [parameters_delta-3/](parameters_delta-3/) and [parameters_delta-4/](parameters_delta-4/).

## Additional Validation Data
### Different Datasets
We run additional validation at 10b token intervals over FineWeb, FineWeb-Edu and DCLM data. See [benchmarks/fineweb_loss_plot.py](benchmarks/fineweb_loss_plot.py) for the code to run this validation. The code to preprocess the data, collect loss and plot is all contained in the folder.
Our validation losses are stored, per sample, in [other_validation_losses/](other_validation_losses/) and aggregated in [benchmarks/fineweb_edu_losses_combined.jsonl](benchmarks/fineweb_edu_losses_combined.jsonl) and [benchmarks/fineweb_dclm_losses_combined.jsonl](benchmarks/fineweb_dclm_losses_combined.jsonl).

### FineWeb Benchmarks
We run the FineWeb Benchmarks [benchmarks/lighteval_tasks.py](benchmarks/lighteval_tasks.py) (Note: updated to work with lighteval `lighteval==0.8.1`). An example command is provided in [shells/benchmarking.sh](shells/benchmarking.sh). Our evaluation metrics are stored in [benchmarks/light_eval_df.parquet](benchmarks/light_eval_df.parquet).

## Plotting
We provide bash commands to run all code needed in [plotting.sh](shells/plotting.sh), due to the large compute requirements to run the grid searches in many parts of this code, we provide our cache files [here](https://huggingface.co/datasets/smcleish/scaling-laws-cache), please read the README there for how to use it. 
This should be placed:
```
gemstone-scaling-laws
└── plotters
    └── data_cache
```

### Approach 3
We use [approach_3_brute_force.py](plotters/approach_3_brute_force.py) to plot the output of approach 3 width-depth laws using brute force search.

### Other plots
* Loss over muliple validation datasets in plotted in [benchmarks/fineweb_loss_plot.py](benchmarks/fineweb_loss_plot.py).
* Benchmark scaling laws to predict error are fitted in [benchmarks/gadre_fit.py](benchmarks/gadre_fit.py) and to predict accuracy are fitted in [benchmarks/bhagia_fit.py](benchmarks/bhagia_fit.py).
* The "Width/Depth vs. Compute/Time Continuum" plot is in [plotters/approach_1_shade_by_wd_ratio.py](plotters/approach_1_shade_by_wd_ratio.py).
* Benchmark performance is plotted in [benchmarks/plot_lighteval.py](benchmarks/plot_lighteval.py).
* The rainbow of scaling laws is plotted inside of [rainbow.py](plotters/rainbow.py). This requires the correct approach 1 and approach 3 laws to have been created.
* Plotting of overtraining parabolas is done in [overtrain_parabola.py](plotters/overtrain_parabola.py). This requires the correct part of [approach_3_brute_force.py](plotters/approach_3_brute_force.py) to have ran before hand to cache outputs correctly. Caution: this is currently hard coded to point to only the files we use in the paper.
* Overspending analysis is done inside of [approach_1.py](plotters/approach_1.py).
* Chinchilla Reduced Sampling is visualised in [chinchilla_reduced_sampling.py](chinchilla_reduced_sampling.py).
* Analysis of delta and grid search sizes in done in  [slope_analysis.py](plotters/slope_analysis.py)
* Plotting for feasible model shapes is done in [plot_feasible_model_shapes_paper_plots.ipynb](plot_feasible_model_shapes_paper_plots.ipynb).
* Plotting for \(\mu P\) is done in [plot_mup.py](plot_mup.py).
* Loss curves are plotted in [wandb_data_plot.py](wandb_data_plot.py).

## Contact
Please, feel free to contact us with any questions, or open an issue on Github.

## Acknowledgements
We used [Resolving Discrepancies in Compute-Optimal Scaling of Language Models](https://github.com/formll/resolving-scaling-law-discrepancies) to guide the format of this code base.
We use the [Epoch AI Analyzing Chinchilla](https://github.com/epoch-research/analyzing-chinchilla) data in `data/`.
