import numpy as np
import sys
import os
import pandas as pd
from scipy.linalg import sqrtm
import matplotlib.pyplot as plt
from matplotlib import colors
import ipywidgets as widgets
from IPython.display import display, clear_output
from matplotlib.colors import Normalize, BoundaryNorm, ListedColormap



#################################################################################################################################################################################

                                            ####################     ENGINEERING PUMPING SCHEME     ####################

#################################################################################################################################################################################

def generate_Gk_plus(M, k):
    """
    Generate the “+” frequency-conversion coupling matrix G_k^+ of size M×M for a given offset k.
    Non-zero entries lie on the k-th off-diagonals with alternating ±1 patterns.
    """
    k_abs = np.abs(k)           # absolute value of the frequency index
    G = np.zeros((M, M))        # initialize M×M zero matrix
    j = 0                        # counter for successive diagonal steps

    # Only proceed if k is non-zero
    if k_abs > 0:
        # Loop while the target indices remain within matrix bounds
        while (k_abs + 2*j <= M-1) and (k_abs + 2*j + 1 < M):
            if j == 0:
                # For the first pairing, place +1 at (k_abs, 0) and –1 at (1, k_abs+1)
                G[k_abs, 0]         = 1
                G[1, k_abs + 1]     = -1
            else:
                # For further diagonals, shift by 2*j in both row and column
                G[k_abs + 2*j, 2*j]                 = 1
                G[2*j + 1, k_abs + 2*j + 1]         = -1
            j += 1  # move to the next diagonal step

        # If M + k_abs is odd, place an extra +1 at the wrap‑around position
        if (M + k_abs) % 2 != 0:
            G[M-1, M-1 - k_abs] = 1

    return G


def generate_Gammak_plus(M, k):
    """
    Generate the “+” squeezing coupling matrix Γ_k^+ of size M×M for a given offset k.
    Non-zero entries lie on the k-th anti-diagonals with +1 pattern.
    """
    Gamma = np.zeros((M, M))  # initialize M×M zero matrix
    j = 0                     # counter for successive anti-diagonal steps
    k_abs = np.abs(k)         # absolute value of the squeezing index

    if k == 0:
        # Main anti-diagonal (k=0): place +1 at (2j, M-2j-1) while within bounds
        while (M - 1 - 2*j > 0):
            Gamma[2*j, M - 2*j - 1] = 1
            j += 1

    elif k > 0:
        # Positive k: shift starting row by k_abs, keep placing on anti-diagonal
        while (M - 1 - k_abs - 2*j >= 0):
            Gamma[2*j + k_abs, M - 1 - 2*j] = 1
            j += 1

    else:
        # Negative k: shift starting column of anti-diagonal by k_abs
        while (M - 1 - k_abs - 2*j >= 0):
            Gamma[2*j, M - 1 - k_abs - 2*j] = 1
            j += 1

    return Gamma


def generate_Gk_minus(Gk_plus):
    """
    Generate the “–” frequency-conversion matrix G_k^- by transposing G_k^+.
    """
    return Gk_plus.T


def generate_Gammak_minus(M, k):
    """
    Generate the “–” squeezing coupling matrix Γ_k^- of size M×M for a given offset k.
    Non-zero entries lie on anti-diagonals with –1 pattern, offset by k.
    """
    Gamma = np.zeros((M, M))  # initialize M×M zero matrix
    j = 0                     # counter for successive anti-diagonal steps
    k_abs = abs(k)            # absolute value of the squeezing index

    if k == 0:
        # Main anti-diagonal: place –1 at (2j+1, M-2-2j)
        while M - 2 - 2*j >= 0:
            Gamma[2*j + 1, M - 2 - 2*j] = -1
            j += 1

    elif k > 0:
        # Positive k: shift starting row by (k_abs + 1)
        while M - 2 - k_abs - 2*j >= 0:
            Gamma[2*j + k_abs + 1, M - 2 - 2*j] = -1
            j += 1

    else:
        # Negative k: shift starting column by k_abs
        while M - 2 - k_abs - 2*j >= 0:
            Gamma[2*j + 1, M - 2 - k_abs - 2*j] = -1
            j += 1

    return Gamma

def generate_G_set(N_m):
    """
    Generate normalized sets of frequency-conversion coupling matrices G_k^+ and G_k^-.

    Parameters:
    -----------
    N_m : int
        Number of mode pairs; matrix dimension will be 2*N_m.

    Returns:
    --------
    G_plus_set : list of ndarray
        List of normalized G_k^+ matrices for k = 0, 1, ..., N_m-1.
    G_minus_set : list of ndarray
        Corresponding list of normalized G_k^- matrices.
    """
    # Define k values from 0 to N_m-1 in steps of 1
    dk = 1
    k_s = 1
    k_e = N_m
    k_arr = np.arange(k_s, k_e, dk)

    # Initialize lists to hold the normalized matrices
    G_plus_set = []
    G_minus_set = []

    # Loop over each frequency-offset index k_i
    for k_i in k_arr:
        # Compute the normalization constant ℱ = 2·(N_m – |k_i|)
        G_conv = 2 * (N_m - np.abs(k_i))

        # Build the raw coupling matrices of size (2N_m × 2N_m)
        Gk_plus  = generate_Gk_plus(2 * N_m, 2 * k_i)
        Gk_minus = generate_Gk_minus(Gk_plus)

        # Normalize each matrix by 1/sqrt(G_conv) and append to lists
        G_plus_set.append(Gk_plus)    #/ np.sqrt(G_conv)                
        G_minus_set.append(Gk_minus)  #/ np.sqrt(G_conv)

    return G_plus_set, G_minus_set


def generate_Gamma_set(N_m):
    """
    Generate normalized sets of squeezing coupling matrices Γ_k^+ and Γ_k^-.

    Parameters:
    -----------
    N_m : int
        Number of mode pairs; matrix dimension will be 2*N_m.

    Returns:
    --------
    Gamma_plus_set : list of ndarray
        List of normalized Γ_k^+ matrices for k = -N_m+1, ..., N_m-1.
    Gamma_minus_set : list of ndarray
        Corresponding list of normalized Γ_k^- matrices.
    """
    # Define k values from -N_m+1 to N_m-1 in steps of 1
    dk = 1
    k_s = -N_m + 1
    k_e = N_m
    k_arr = np.arange(k_s, k_e, dk)

    # Initialize lists to hold the normalized matrices
    Gamma_plus_set  = []
    Gamma_minus_set = []

    # Loop over each squeezing-offset index k_i
    for k_i in k_arr:
        # Compute normalization constant ℋ = N_m – |k_i|
        Gamma_conv = -np.abs(k_i) + N_m

        # Build the raw coupling matrices of size (2N_m × 2N_m)
        Gammak_plus  = generate_Gammak_plus(2 * N_m, 2 * k_i)
        Gammak_minus = generate_Gammak_minus(2 * N_m, 2 * k_i)

        # Normalize each matrix by 1/sqrt(Gamma_conv) and append to lists
        Gamma_plus_set.append(Gammak_plus)   #/ np.sqrt(Gamma_conv)
        Gamma_minus_set.append(Gammak_minus) #/ np.sqrt(Gamma_conv)

    return Gamma_plus_set, Gamma_minus_set


def plot_S_vs_S_th(S0, S, nmodes):
    """
    Plots a comparison between two complex scattering matrices: S0 (reference) and S (target).
    
    Parameters:
    -----------
    S0 : np.ndarray
        Reference complex scattering matrix.
    S  : np.ndarray
        Target scattering matrix to be compared.
    nmodes : int
        Number of modes; used to set the axis limits for the plots.
    
    Returns:
    --------
    fig : matplotlib.figure.Figure
        The figure object containing the plots.
    axes : np.ndarray of matplotlib.axes._subplots.AxesSubplot
        Array of subplot axes.
    """
    
    # Compute the number of modes on each side of the axis center (assumes symmetric indices)
    top = nmodes // 2

    # Calculate the magnitudes of both matrices
    mag_S0 = np.abs(S0)
    mag_S  = np.abs(S)

    # Compute the phases of both matrices in degrees, wrapped to [0, 360)
    phi_S0 = np.mod(np.angle(S0), 2*np.pi) * 180 / np.pi
    phi_S  = np.mod(np.angle(S) , 2*np.pi) * 180 / np.pi

    # Define color limits for consistent scaling across plots
    vmin_mag, vmax_mag = np.min([mag_S0.min(), mag_S.min()]), np.max([mag_S0.max(), mag_S.max()])
    vmin_phi, vmax_phi = 0, 360

    # Create a 2x2 subplot figure
    fig, axes = plt.subplots(2, 2, figsize=(20, 15), constrained_layout=True)

    # First row: plot magnitudes using a diverging colormap
    for ax, data, title in zip(
        axes[0],
        [mag_S0, mag_S],
        ['$|S_0|$', '$|S_{th}|$']  # Titles: reference and target magnitudes
    ):
        im = ax.imshow(
            data,
            cmap='pink_r',
            vmin=vmin_mag, vmax=vmax_mag,
            interpolation='nearest',
            extent=[-top, top, top, -top]  # Set axis to range from -top to +top
        )
        ax.set_title(title)
        cbar = fig.colorbar(
            im, ax=ax, orientation='vertical',
            fraction=0.046, pad=0.04
        )
        cbar.set_label('a.u.', rotation=90, labelpad=10)

    # Second row: plot phases using a cyclic colormap
    for ax, data, title in zip(
        axes[1],
        [phi_S0, phi_S],
        ['$\\angle S_0$', '$\\angle S_{th}$']  # Titles: reference and target phases
    ):
        im = ax.imshow(
            data,
            cmap='twilight',
            vmin=vmin_phi, vmax=vmax_phi,
            interpolation='nearest',
            extent=[-top, top, top, -top]
        )
        ax.set_title(title)
        cbar = fig.colorbar(im, ax=ax, orientation='vertical', fraction=0.046, pad=0.04)
        cbar.set_ticks([0, 90, 180, 270, 360])
        cbar.set_ticklabels(['0°', '90°', '180°', '270°', '360°'])

    plt.show()
    return fig, axes




def M_reconstructed_from_S(S, K, Id):
    """
    Reconstructs a complex matrix M from a given scattering matrix S using a known transformation matrix K 
    and the identity matrix Id.

    Parameters:
    -----------
    S : np.ndarray
        Complex scattering matrix.
    K : np.ndarray
        Transformation matrix used in the reconstruction formula.
    Id : np.ndarray
        Identity matrix of the same shape as S.

    Returns:
    --------
    M_reconstructed : np.ndarray
        The reconstructed complex matrix M, with small numerical noise suppressed.
    """
    
    # Apply the reconstruction formula: M = i K · (S + I)^(-1) · K
    M_rec = 1j * K.dot(np.linalg.inv(S + Id)).dot(K)

    # Threshold for zeroing out very small elements
    eps = 1e-12

    # Extract magnitude and phase of the reconstructed matrix
    mag_rec = np.abs(M_rec)
    phi_rec = np.mod(np.angle(M_rec), 2 * np.pi)  # Phase in the [0, 2π) range

    # Identify elements with negligible magnitude
    mask = mag_rec < eps

    # Rebuild matrix using cleaned magnitude and phase
    M_rec_adj = mag_rec * np.exp(1j * phi_rec)
    
    # Set very small elements exactly to zero to suppress numerical noise
    M_rec_adj[mask] = 0

    # Final cleaned-up version of the reconstructed matrix
    M_reconstructed = M_rec_adj

    return M_reconstructed




def compute_pumping_scheme(nmodes, g1_value, M_reconstructed, epsilon):
    """
    Computes the amplitudes and phases of the pumps needed to reproduce a given interaction matrix M.
    The function decomposes M into contributions from squeezing and frequency-conversion operators, 
    and calculates the corresponding pump strengths and phases.

    Parameters:
    -----------
    nmodes : int
        Number of frequency modes in the system.
    g1_value : float
        Reference coupling strength (scaling factor for normalization).
    M_reconstructed : np.ndarray
        The complex interaction matrix previously reconstructed (typically from scattering data).

    Returns:
    --------
    magnitudes : np.ndarray
        Amplitudes of the frequency-conversion pumps (Γ⁺).
    phases : np.ndarray
        Phases (in degrees) of the frequency-conversion pumps (Γ⁺).
    magnitudes_ : np.ndarray
        Amplitudes of the squeezing pumps (G⁺).
    phases_ : np.ndarray
        Phases (in degrees) of the squeezing pumps (G⁺).
    """
    
    N_m = nmodes
    gamma_k_arr = np.arange(-N_m + 1, N_m)  # Range of frequency-conversion detunings

    # Generate sets of operators: squeezing (G±) and frequency-conversion (Γ±)
    G_plus_set, G_minus_set = generate_G_set(N_m)
    Gamma_plus_set, Gamma_minus_set = generate_Gamma_set(N_m)

    # Remove diagonal from M: only off-diagonal terms are considered for pump decomposition
    diag_vec = np.diag(M_reconstructed)
    M_no_diag = M_reconstructed.copy()
    np.fill_diagonal(M_no_diag, 0)

    # Compute coefficients for squeezing terms (G⁺ and G⁻) via inner products
    coeff_G_plus = np.array([
        np.trace(G_plus_set[k].T @ M_no_diag)
        for k in range(N_m - 1)
    ]) * (-1) / (g1_value)

    coeff_G_minus = np.array([
        np.trace(G_minus_set[k].T @ M_no_diag)
        for k in range(N_m - 1)
    ]) * (-1) / (g1_value)

    # Compute coefficients for frequency-conversion terms (Γ⁺ and Γ⁻)
    coeff_Γ_plus = np.array([
        np.trace(Gamma_plus_set[i].T @ M_no_diag)
        for i in range(len(gamma_k_arr))
    ]) * (-1) / (g1_value)

    coeff_Γ_minus = np.array([
        np.trace(Gamma_minus_set[i].T @ M_no_diag)
        for i in range(len(gamma_k_arr))
    ]) * (-1) / (g1_value)

    # Set very small coefficients to zero (to suppress noise and improve interpretability)
    coeff_G_plus[np.abs(coeff_G_plus) < epsilon] = 0
    coeff_G_minus[np.abs(coeff_G_minus) < epsilon] = 0
    coeff_Γ_plus[np.abs(coeff_Γ_plus) < epsilon] = 0
    coeff_Γ_minus[np.abs(coeff_Γ_minus) < epsilon] = 0

    # Prepare k-values and normalization factors for scaling pump amplitudes
    Nm = (len(coeff_Γ_plus) + 1) // 2  # Number of detunings for frequency conversion
    k_arr = np.arange(-Nm + 1, Nm)
    C = 1 / (-np.abs(k_arr) + N_m)  # Normalization factor for Γ terms

    k_arr_conv = np.arange(1, Nm)
    C_conv = 1 / (2 * (N_m - np.abs(k_arr_conv)))  # Normalization factor for G terms

    # Convert coefficients to magnitudes and phases in degrees
    magnitudes_Γ_plus       = np.abs(coeff_Γ_plus) * C 
    phases_Γ_plus           = np.angle(coeff_Γ_plus) / np.pi * 180
    magnitudes_Γ_minus      = np.abs(coeff_Γ_minus) * C 
    phases_Γ_minus          = np.angle(coeff_Γ_minus) / np.pi * 180

    magnitudes_G_plus       = np.abs(coeff_G_plus) * C_conv 
    phases_G_plus           = np.angle(coeff_G_plus) / np.pi * 180
    magnitudes_G_minus      = np.abs(coeff_G_minus) * C_conv 
    phases_G_minus          = np.angle(coeff_G_minus) / np.pi * 180

    return k_arr, k_arr_conv, magnitudes_Γ_plus, phases_Γ_plus, magnitudes_Γ_minus, phases_Γ_minus, magnitudes_G_plus, phases_G_plus, magnitudes_G_minus, phases_G_minus

def compute_pumping_scheme_Fabio(nmodes, g1_value, M_reconstructed, epsilon):
    """
    Computes the amplitudes and phases of the pumps needed to reproduce a given interaction matrix M.
    The function decomposes M into contributions from squeezing and frequency-conversion operators, 
    and calculates the corresponding pump strengths and phases.

    Parameters:
    -----------
    nmodes : int
        Number of frequency modes in the system.
    g1_value : float
        Reference coupling strength (scaling factor for normalization).
    M_reconstructed : np.ndarray
        The complex interaction matrix previously reconstructed (typically from scattering data).

    Returns:
    --------
    magnitudes : np.ndarray
        Amplitudes of the frequency-conversion pumps (Γ⁺).
    phases : np.ndarray
        Phases (in degrees) of the frequency-conversion pumps (Γ⁺).
    magnitudes_ : np.ndarray
        Amplitudes of the squeezing pumps (G⁺).
    phases_ : np.ndarray
        Phases (in degrees) of the squeezing pumps (G⁺).
    """
    
    N_m = nmodes
    gamma_k_arr = np.arange(-N_m + 1, N_m)  # Range of frequency-conversion detunings

    # Generate sets of operators: squeezing (G±) and frequency-conversion (Γ±)
    G_plus_set, G_minus_set = generate_G_set(N_m)
    Gamma_plus_set, Gamma_minus_set = generate_Gamma_set(N_m)

    # Remove diagonal from M: only off-diagonal terms are considered for pump decomposition
    diag_vec = np.diag(M_reconstructed)
    M_no_diag = M_reconstructed.copy()
    np.fill_diagonal(M_no_diag, 0)

    # Compute coefficients for squeezing terms (G⁺ and G⁻) via inner products
    coeff_G_plus = np.array([
        np.trace(G_plus_set[k].T @ M_no_diag)
        for k in range(N_m - 1)
    ]) * (-1) / (g1_value)

    coeff_G_minus = np.array([
        np.trace(G_minus_set[k].T @ M_no_diag)
        for k in range(N_m - 1)
    ]) * (-1) / (g1_value)

    # Compute coefficients for frequency-conversion terms (Γ⁺ and Γ⁻)
    coeff_Γ_plus = np.array([
        np.trace(Gamma_plus_set[i].T @ M_no_diag)
        for i in range(len(gamma_k_arr))
    ]) * (-1) / (g1_value)

    coeff_Γ_minus = np.array([
        np.trace(Gamma_minus_set[i].T @ M_no_diag)
        for i in range(len(gamma_k_arr))
    ]) * (-1) / (g1_value)

    # Set very small coefficients to zero (to suppress noise and improve interpretability)
    coeff_G_plus[np.abs(coeff_G_plus) < epsilon] = 0
    coeff_G_minus[np.abs(coeff_G_minus) < epsilon] = 0
    coeff_Γ_plus[np.abs(coeff_Γ_plus) < epsilon] = 0
    coeff_Γ_minus[np.abs(coeff_Γ_minus) < epsilon] = 0

    # Prepare k-values and normalization factors for scaling pump amplitudes
    Nm = (len(coeff_Γ_plus) + 1) // 2  # Number of detunings for frequency conversion
    k_arr = np.arange(-Nm + 1, Nm)
    C = 1 / (-np.abs(k_arr) + N_m)  # Normalization factor for Γ terms

    k_arr_conv = np.arange(1, Nm)
    C_conv = 1 / (2 * (N_m - np.abs(k_arr_conv)))  # Normalization factor for G terms

    # Convert coefficients to magnitudes and phases in degrees
    magnitudes_Γ_plus       = np.abs(coeff_Γ_plus) * C * 2
    phases_Γ_plus           = np.angle(coeff_Γ_plus) #/ np.pi * 180
    magnitudes_Γ_minus      = np.abs(coeff_Γ_minus) * C * 2
    phases_Γ_minus          = np.angle(coeff_Γ_minus) #/ np.pi * 180

    magnitudes_G_plus       = np.abs(coeff_G_plus) * C_conv * 2
    phases_G_plus           = np.angle(coeff_G_plus) #/ np.pi * 180
    magnitudes_G_minus      = np.abs(coeff_G_minus) * C_conv * 2
    phases_G_minus          = np.angle(coeff_G_minus) #/ np.pi * 180

    return k_arr, k_arr_conv, magnitudes_Γ_plus, phases_Γ_plus, magnitudes_Γ_minus, phases_Γ_minus, magnitudes_G_plus, phases_G_plus, magnitudes_G_minus, phases_G_minus



# -------------------------------------------------------------
# Function to scale and mask magnitudes based on threshold bins
# -------------------------------------------------------------
def scale_and_mask(mag, magnitudes_Γ_plus, magnitudes_G_plus):
    """
    Scale magnitude values into visual bins and create masks for each region.

    Parameters
    ----------
    mag : array_like
        Original magnitude values.
    thr_abs : float
        Absolute threshold below which values remain unscaled.
    bins : sequence of (lo_rel, hi_rel)
        Relative bin boundaries in [0,1], to be multiplied by max(mag).
    scales : sequence of float
        Scaling factors for each bin; len(scales) must == len(bins).

    Returns
    -------
    mag_scaled : ndarray
        Magnitudes after applying bin-specific scaling factors.
    masks : dict
        Dictionary of boolean masks for each region:
        - 'orig': values <= thr_abs (unscaled region)
        - 0,1,…: masks for each bin in `bins`
    """
    mag = np.asarray(mag)
    mag_scaled = mag.copy()
    masks = {}

    # 1) Compute the initial maximum for relative thresholds
    max_init = mag.max()

    # 2) Unscaled region: everything <= absolute threshold
    masks['orig'] = mag <= thr_abs

    # 3) Loop through each relative bin
    for i, (lo_rel, hi_rel) in enumerate(bins):
        lo = lo_rel * max_init
        hi = hi_rel * max_init
        mask = (mag > lo) & (mag <= hi)
        mag_scaled[mask] *= scales[i]
        masks[i] = mask

    return mag_scaled, masks


# -------------------------------------------------------------
# Function to plot stem markers by group and color scale
# -------------------------------------------------------------
def plot_group(ax, x, mag_orig, mag_scaled, masks, base_cmap):
    """
    Plot stem markers on a given axis, coloring by magnitude bins.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Axis on which to plot stems.
    x : array_like
        x positions for each data point.
    mag_orig : array_like
        Original magnitudes for unscaled plotting.
    mag_scaled : array_like
        Scaled magnitudes for colored bins.
    masks : dict
        Boolean masks from `scale_and_mask` identifying regions.

    Notes
    -----
    - `base_cmap`, `cmap6`, and `norm6` should be defined in outer scope.
    - Bins and scales must match those used in `scale_and_mask`.
    """
    # 1) Plot unscaled region (orig) using the base colormap index 0
    mask0 = masks['orig']
    if np.any(mask0):
        # Create stem plot: linefmt sets line color, markerfmt the point marker
        line, stems, _ = ax.stem(
            x[mask0], mag_orig[mask0],
            linefmt=base_cmap(0), markerfmt='o', basefmt=' '
        )
        # Ensure both stem lines and markers use the same base color
        line.set_color(base_cmap(0))
        stems.set_color(base_cmap(0))

    # 2) Plot each bin region with corresponding color
    for i in range(len(bins)):
        mask = masks[i]
        if np.any(mask):
            # Determine color for this bin based on its midpoint
            mid_rel = (bins[i][0] + bins[i][1]) / 2
            color = cmap6(norm6(mid_rel))
            # Plot scaled values at their x positions
            line, stems, _ = ax.stem(
                x[mask], mag_scaled[mask],
                linefmt=color, markerfmt='o', basefmt=' '
            )
            # Apply the computed color to stems and markers
            line.set_color(color)
            stems.set_color(color)

# -------------------------------------------------------------
# Function to compute aligned real matrix square root
# -------------------------------------------------------------
def real_Msqrt_aligned(V):
    """
    Compute the real square root of a symmetric matrix V using eigen-decomposition.

    Parameters
    ----------
    V : array_like, shape (n, n)
        Symmetric (Hermitian) input matrix.

    Returns
    -------
    sqrtV : ndarray
        The matrix square root satisfying sqrtV @ sqrtV ≈ V.
    """
    # 1) Eigen-decompose V: V = U @ diag(d) @ U^(-1)
    d, U = np.linalg.eigh(V)
    # 2) Compute square roots of eigenvalues
    sq_d = np.emath.sqrt(d)
    sqD = np.diag(sq_d)
    # 3) Compute inverse (or conjugate transpose for unitary U)
    Udag = np.linalg.inv(U)
    # 4) Reconstruct square root: U @ sqrt(diag(d)) @ U^(-1)
    sqrtV = U.dot(sqD).dot(Udag)

    return sqrtV

# -------------------------------------------------------------
# Function to create a matrix with main diagonal and anti-diagonal
# -------------------------------------------------------------
def create_V(n, diag_val, antidiag_val):
    """
    Create a 2n×2n matrix V with specified diagonal and anti-diagonal values.

    Parameters
    ----------
    n : int
        Half-size of the matrix; output is (2n)×(2n).
    diag_val : float
        Value to place on the main diagonal.
    antidiag_val : float
        Value to place on the secondary (anti-) diagonal.

    Returns
    -------
    V : ndarray
        The constructed matrix.
    """
    # Initialize a 2n×2n zero matrix
    V = np.zeros((2*n, 2*n))
    # Fill main diagonal positions (i, i)
    np.fill_diagonal(V, diag_val)
    # To fill anti-diagonal (i, 2n-1-i), flip horizontally and fill its diagonal
    flipped = np.fliplr(V)
    np.fill_diagonal(flipped, antidiag_val)
    # (flipped is a view, so V is modified in place)
    return V

# -------------------------------------------------------------
# Function to create a matrix with diagonal and multiple upper anti-diagonals
# -------------------------------------------------------------
def create_diag_and_upper_antidiag(n, diag_val, anti_upper_val, offset_list, sign_list):
    """
    Create an n×n matrix V with:
      - diag_val on the main diagonal V[i,i]
      - anti_upper_val (with per-offset sign) on each upper anti‑diagonal
        defined by i + j == offset, for offsets in offset_list.
    
    Parameters
    ----------
    n : int
        Size of the square matrix.
    diag_val : float
        Value on the main diagonal (i, i).
    anti_upper_val : float
        Base value to place on the anti-diagonals; will be flipped by sign_list.
    offset_list : array_like of int
        Each offset defines one “upper anti‑diagonal” via i+j == offset.
    sign_list : array_like of str
        Same length as offset_list; each entry must be "pos" or "neg".  
        If "neg", the placed value is -anti_upper_val; if "pos", +anti_upper_val.
    
    Returns
    -------
    V : ndarray, shape (n, n)
        The constructed matrix.
    """
    # Initialize to zeros
    V = np.zeros((n, n), dtype=float)

    # 1) Main diagonal
    np.fill_diagonal(V, diag_val)

    # 2) For each offset and sign, fill that anti-diagonal
    for offset, sign in zip(offset_list, sign_list):
        # Determine signed value
        if sign.lower() == "neg":
            val = -anti_upper_val
        elif sign.lower() == "pos":
            val = +anti_upper_val
        else:
            raise ValueError(f"sign_list entries must be 'pos' or 'neg', got {sign!r}")

        # Compute all (i,j) with i+j == offset
        rows = np.arange(n)
        cols = offset - rows
        valid = (cols >= 0) & (cols < n)

        # Assign
        V[rows[valid], cols[valid]] = val

    return V



def plt_mag_pha_Matrix(Matrix, label: str):
    """
    Plot magnitude and phase of a complex-valued 2D array.

    Parameters
    ----------
    Matrix : array_like, shape (n, n)
        Complex-valued input matrix.
    label : str
        LaTeX-ready string to use in plotting titles, e.g. "S_{xp}" or "\\sqrt{V_0}".
    """
    # compute scale for magnitude
    scale = np.max(np.abs(Matrix))
    top   = len(Matrix) // 2

    # set up figure
    fig, axes = plt.subplots(1, 2, figsize=(20, 7), constrained_layout=True)

    # 1) Magnitude |Matrix|
    im0 = axes[0].imshow(
        np.abs(Matrix),
        cmap='RdBu_r',
        vmin=-scale, vmax=scale,                    
        extent=[-top, top, top, -top]
    )
    axes[0].set_title(r'$|\,' + label + r'\,|$')
    cbar0 = fig.colorbar(im0, ax=axes[0], orientation='vertical',
                         fraction=0.046, pad=0.04)
    cbar0.set_label('a.u.', rotation=90, labelpad=10)

    # 2) Phase arg(Matrix)
    im1 = axes[1].imshow(
        np.angle(Matrix),
        cmap='twilight',
        vmin=0, vmax=2*np.pi,
        extent=[-top, top, top, -top]
    )
    axes[1].set_title(r'$\mathrm{arg}(\,' + label + r'\,)$')
    cbar1 = fig.colorbar(im1, ax=axes[1], orientation='vertical', fraction=0.046, pad=0.04)
    ticks = [0, np.pi/2, np.pi, 3*np.pi/2, 2*np.pi]
    cbar1.set_ticks(ticks)
    cbar1.set_ticklabels(['0', '90°', '180°', '270°', '360°'])


    plt.show()


# -------------------------------------------------------------
# Function to scale and mask magnitudes based on threshold bins
# -------------------------------------------------------------
def scale_and_mask(mag, reference_max=None):
    """
    Scale magnitude values into visual bins and create masks for each region.

    Parameters
    ----------
    mag : array_like
        Original magnitude values.
    reference_max : float, optional
        Maximum reference value to define absolute thresholds.
        If None, uses mag.max().

    Returns
    -------
    mag_scaled : ndarray
        Magnitudes after applying bin-specific scaling factors.
    masks : dict
        Dictionary of boolean masks for each region:
        - 'orig': values below the absolute threshold (unscaled)
        - 0,1,...,5: each of the six bins defined in logarithmic space
    """
    mag = np.asarray(mag)
    max_val = float(reference_max if reference_max is not None else mag.max())

    # Absolute threshold below which values remain unscaled
    thr_abs = 1e-6 * max_val

    # Define logarithmic bins from 10^-7 to 10^0
    thresholds = np.logspace(-7, 0, 8)
    bins = [(thresholds[i], thresholds[i+1]) for i in range(len(thresholds)-1)]
    scales = {i: 1/bin_lo for i, (bin_lo, _) in enumerate(bins)}

    # Prepare outputs
    mag_scaled = mag.copy().astype(float)
    masks = {}

    # Mask for unscaled (orig)
    masks['orig'] = mag <= thr_abs

    # Masks and scaling for each bin
    for i, (lo_rel, hi_rel) in enumerate(bins):
        lo = lo_rel * max_val
        hi = hi_rel * max_val
        mask = (mag > lo) & (mag <= hi)
        mag_scaled[mask] *= scales[i]
        masks[i] = mask

    return mag_scaled, masks


def plot_group(ax, x, mag_orig, mag_scaled, masks, cmap6, norm6, bins):
    """
    Plot stem markers on a given axis, coloring by magnitude bins.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Axis on which to plot stems.
    x : array_like
        x positions for each data point.
    mag_orig : array_like
        Original magnitudes for unscaled plotting.
    mag_scaled : array_like
        Scaled magnitudes for colored bins.
    masks : dict
        Boolean masks identifying regions (as from scale_and_mask).
    cmap6 : ListedColormap
        Colormap with six discrete colors.
    norm6 : BoundaryNorm
        Normalization mapping values to colormap bins.
    bins : list of tuple
        List of (lower_rel, upper_rel) boundaries for each bin.
    """
    # 1) Plot unscaled region
    mask0 = masks.get('orig')
    if mask0 is not None and np.any(mask0):
        line, stems, _ = ax.stem(
            x[mask0], mag_orig[mask0],
            linefmt='gray', markerfmt='o', basefmt=' '
        )
        line.set_color('gray')
        stems.set_color('gray')

    # 2) Plot each bin region with corresponding color
    reference_max = mag_orig.max()
    for i, (lo_rel, hi_rel) in enumerate(bins):
        mask = masks.get(i)
        if mask is None or not np.any(mask):
            continue
        # Midpoint in relative units for color lookup
        mid_rel = (lo_rel + hi_rel) / 2
        color = cmap6(norm6(mid_rel))
        line, stems, _ = ax.stem(
            x[mask], mag_scaled[mask],
            linefmt=color, markerfmt='o', basefmt=' '
        )
        line.set_color(color)
        stems.set_color(color)


def pumping_from_covariance(
    nmodes,
    diag,
    adiag,
    offset_list, 
    sign_list,
    gamma_int,
    gamma_ext,
    g1_value,
    gamma_over_g,
    sum_amp,
):

    gamma_r      = g1_value * gamma_over_g   # Reference rate (GHz)
    gamma0_ext   = gamma_ext * gamma_r       # Scaled external coupling rate (GHz)
    
    # Identity matrix of size 2·nmodes for quadrature space
    Id = np.identity(2 * nmodes, dtype=complex)
    
    # Coupling matrix K: diagonal with sqrt of external rates
    dim = 2 * nmodes
    K = np.identity(dim) * np.sqrt(gamma0_ext)  # Assumes equal coupling for each quadrature

    # Total dimension for convenience
    N = dim
    
    # Build initial coupling matrix V0 with given diag/adiag pattern
    V0 = create_diag_and_upper_antidiag(N, diag, adiag, offset_list, sign_list)

    # --- Compute and plot square-root decomposition ---
    sqrtV = real_Msqrt_aligned(V0)          # Real-aligned matrix square root

    # Unitary transformation U (2×2 block Hadamard with phase)
    U_2by2 = (1/np.sqrt(2)) * np.array([[1,  1j],
                                       [1, -1j]])
    Udag_2by2 = (1/np.sqrt(2)) * np.array([[ 1,  1 ],
                                         [-1j, 1j]])
    # Expand U to full dimension as block diagonal
    U = np.kron(np.eye(nmodes, dtype=complex), U_2by2)
    Udag = np.linalg.inv(U)  # Hermitian adjoint (inverse for unitary)
    
    # Transform square-root matrix into (a, a^†) basis
    Saadag = U.dot(sqrtV).dot(Udag)

    
    # --- Reconstruct measurement matrix M and compute pump response ---
    M = M_reconstructed_from_S(Saadag, K, Id)
    (k_arr, k_arr_conv,
     magnitudes_Γ_plus, phases_Γ_plus,
     magnitudes_Γ_minus, phases_Γ_minus,
     magnitudes_G_plus, phases_G_plus,
     magnitudes_G_minus, phases_G_minus) = compute_pumping_scheme(nmodes, g1_value, M)
    
    # --- Renormalize amplitudes so their total sum equals `sum_amp` ---
    # Compute current total of all magnitudes, including both plus and minus channels
    total_current = (
        np.sum(magnitudes_Γ_plus) + np.sum(magnitudes_Γ_minus) +
        np.sum(magnitudes_G_plus) + np.sum(magnitudes_G_minus)
    )
    norm_factor = sum_amp / total_current  # Scaling factor to achieve desired sum
    # Apply normalization to all four channel arrays
    magnitudes_Γ_plus  *= norm_factor
    magnitudes_Γ_minus *= norm_factor
    magnitudes_G_plus  *= norm_factor
    magnitudes_G_minus *= norm_factor
    
    return {
        'k_arr': k_arr,
        'k_arr_conv': k_arr_conv,
        'magnitudes_Γ_plus': magnitudes_Γ_plus,
        'phases_Γ_plus': phases_Γ_plus,
        'magnitudes_Γ_minus': magnitudes_Γ_minus,
        'phases_Γ_minus': phases_Γ_minus,
        'magnitudes_G_plus': magnitudes_G_plus,
        'phases_G_plus': phases_G_plus,
        'magnitudes_G_minus': magnitudes_G_minus,
        'phases_G_minus': phases_G_minus
    } 






def comp_pump_scheme(nmodes, M_reconstructed, epsilon):
    """
    Computes the amplitudes and phases of the pumps needed to reproduce a given interaction matrix M.
    The function decomposes M into contributions from squeezing and frequency-conversion operators, 
    and calculates the corresponding pump strengths and phases.

    Parameters:
    -----------
    nmodes : int
        Number of frequency modes in the system.
    M_reconstructed : np.ndarray
        The complex interaction matrix previously reconstructed (typically from scattering data).

    Returns:
    --------
    magnitudes : np.ndarray
        Amplitudes of the frequency-conversion pumps (Γ⁺).
    phases : np.ndarray
        Phases (in degrees) of the frequency-conversion pumps (Γ⁺).
    magnitudes_ : np.ndarray
        Amplitudes of the squeezing pumps (G⁺).
    phases_ : np.ndarray
        Phases (in degrees) of the squeezing pumps (G⁺).
    """
    
    N_m = nmodes
    gamma_k_arr = np.arange(-N_m + 1, N_m)  # Range of frequency-conversion detunings

    # Generate sets of operators: squeezing (G±) and frequency-conversion (Γ±)
    G_plus_set, G_minus_set = generate_G_set(N_m)
    Gamma_plus_set, Gamma_minus_set = generate_Gamma_set(N_m)

    # Remove diagonal from M: only off-diagonal terms are considered for pump decomposition
    diag_vec = np.diag(M_reconstructed)
    M_no_diag = M_reconstructed.copy()
    np.fill_diagonal(M_no_diag, 0)

    # Compute coefficients for squeezing terms (G⁺ and G⁻) via inner products
    coeff_G_plus = np.array([
        np.trace(G_plus_set[k].T @ M_no_diag)
        for k in range(N_m - 1)
    ]) * (-1) 

    coeff_G_minus = np.array([
        np.trace(G_minus_set[k].T @ M_no_diag)
        for k in range(N_m - 1)
    ]) * (-1) 

    # Compute coefficients for frequency-conversion terms (Γ⁺ and Γ⁻)
    coeff_Γ_plus = np.array([
        np.trace(Gamma_plus_set[i].T @ M_no_diag)
        for i in range(len(gamma_k_arr))
    ]) * (-1) 

    coeff_Γ_minus = np.array([
        np.trace(Gamma_minus_set[i].T @ M_no_diag)
        for i in range(len(gamma_k_arr))
    ]) * (-1) 

    # Set very small coefficients to zero (to suppress noise and improve interpretability)
    coeff_G_plus[np.abs(coeff_G_plus) < epsilon] = 0
    coeff_G_minus[np.abs(coeff_G_minus) < epsilon] = 0
    coeff_Γ_plus[np.abs(coeff_Γ_plus) < epsilon] = 0
    coeff_Γ_minus[np.abs(coeff_Γ_minus) < epsilon] = 0

    # Prepare k-values and normalization factors for scaling pump amplitudes
    Nm = (len(coeff_Γ_plus) + 1) // 2  # Number of detunings for frequency conversion
    k_arr = np.arange(-Nm + 1, Nm)
    C = 1 / (-np.abs(k_arr) + N_m)**(3/2)  # Normalization factor for Γ terms

    k_arr_conv = np.arange(1, Nm)
    C_conv = 1 / (2 * (N_m - np.abs(k_arr_conv)))**(3/2)  # Normalization factor for G terms

    # Convert coefficients to magnitudes and phases in degrees
    magnitudes_Γ_plus       = np.abs(coeff_Γ_plus) * C * 2
    phases_Γ_plus           = np.angle(coeff_Γ_plus) / np.pi * 180
    magnitudes_Γ_minus      = np.abs(coeff_Γ_minus) * C * 2
    phases_Γ_minus          = np.angle(coeff_Γ_minus) / np.pi * 180

    magnitudes_G_plus       = np.abs(coeff_G_plus) * C_conv * 2
    phases_G_plus           = np.angle(coeff_G_plus) / np.pi * 180
    magnitudes_G_minus      = np.abs(coeff_G_minus) * C_conv * 2
    phases_G_minus          = np.angle(coeff_G_minus) / np.pi * 180

    return k_arr, k_arr_conv, magnitudes_Γ_plus, phases_Γ_plus, magnitudes_Γ_minus, phases_Γ_minus, magnitudes_G_plus, phases_G_plus, magnitudes_G_minus, phases_G_minus




def give_pump_list(k_arr, magnitudes_Γ_plus, phases_Γ_plus, k_arr_conv, magnitudes_G_plus, phases_G_plus, g1_value, amp_threshold):
    """
    Constructs a list of pump tones to be used in a multimode parametric system.

    Parameters:
    - k_arr: list of mode indices for squeezing pumps (Γ_plus)
    - magnitudes_Γ_plus: list of amplitude magnitudes for squeezing pumps
    - phases_Γ_plus: list of phases (in degrees) for squeezing pumps
    - k_arr_conv: list of mode indices for conversion pumps (G_plus)
    - magnitudes_G_plus: list of amplitude magnitudes for conversion pumps
    - phases_G_plus: list of phases (in degrees) for conversion pumps
    - g1_value: normalization factor used to scale conversion amplitudes
    - amp_threshold: minimum relative amplitude for a pump to be included

    Returns:
    - pumps: list of tuples (k, amplitude, phase, is_squeezing)
      where:
        - k is the mode index,
        - amplitude is the relative pump strength (rounded),
        - phase is the pump phase in radians (rounded),
        - is_squeezing is a boolean flag: True for squeezing pump, False for conversion.
    """

    pumps = []

    # Loop over squeezing pumps (Γ_plus), tag as squeezing (True)
    for k, amp, phase in zip(k_arr, magnitudes_Γ_plus, phases_Γ_plus):
        amp_rel = amp  # already normalized
        phase = phase - np.pi   # convert degrees to radians
        if amp_rel > amp_threshold:
            # Append pump info if above threshold
            pumps.append((k, round(amp_rel, 8), round(phase, 12), True))
    
    # Loop over conversion pumps (G_plus), tag as conversion (False)
    for k, amp, phase in zip(k_arr_conv, magnitudes_G_plus, phases_G_plus):
        amp_rel = amp   # normalize amplitude
        phase = phase - np.pi   # convert degrees to radians
        if amp_rel > amp_threshold:
            # Append pump info if above threshold
            pumps.append((k, round(amp_rel, 8), round(phase, 12), False))

    return pumps



def assemble_M(g, gamma,
               G_plus_set, G_minus_set,
               Gamma_plus_set, Gamma_minus_set):
    """
    Assembles the matrix M as:
        M = Σ_k [ g_k G_k^+ + g_k* G_k^- + γ_k Γ_k^+ + γ_k* Γ_k^- ]

    where:
      - g_k are conversion pump amplitudes,
      - γ_k are squeezing pump amplitudes,
      - G_k^± and Γ_k^± are predefined matrices describing the pump-mode coupling structure.
    """
    # Initialize M as a zero matrix with same shape as the G matrices
    M = np.zeros_like(G_plus_set[0], dtype=complex)

    # First add contributions from conversion pumps:
    # g has length (N_m - 1), indexed from 1 to N_m - 1
    for idx, gk in enumerate(g, start=1):
        M += gk * G_plus_set[idx-1]
        M += np.conjugate(gk) * G_minus_set[idx-1]

    # Then add contributions from squeezing pumps:
    # gamma has length (2 * N_m - 1), corresponding to k in [-N_m+1, ..., 0, ..., N_m-1]
    N_m = len(gamma) // 2 + 1
    for offset, γk in enumerate(gamma):
        k = offset - (N_m - 1)  # Convert offset to mode index k
        M += γk * Gamma_plus_set[offset]
        M += np.conjugate(γk) * Gamma_minus_set[offset]

    return M


def build_coeff_vectors(pumps, N_m, g1_value):
    """
    From a list of pump definitions:
        pumps = [(k, amp_rel, phase, is_squeezing), ...]
    builds:
      - g:      complex array of length N_m - 1 for conversion coefficients g_k
      - gamma:  complex array of length 2*N_m - 1 for squeezing coefficients γ_k

    Inputs:
      - k: mode index of the pump (positive for conversion, centered around 0 for squeezing)
      - amp_rel: amplitude of the pump relative to base coupling strength g1_value
      - phase: phase of the pump in radians
      - is_squeezing: True if squeezing pump, False if conversion
    """
    g     = np.zeros(N_m - 1, dtype=complex)
    gamma = np.zeros(2 * N_m - 1, dtype=complex)

    for k, amp_rel, phase, is_sq in pumps:
        coeff = amp_rel * g1_value * np.exp(1j * phase)
        if not is_sq:
            # Conversion pump, valid indices: k in [1, ..., N_m - 1]
            if 1 <= k <= N_m - 1:
                g[k - 1] = coeff
            else:
                raise ValueError(f"Conversion pump index k={k} out of range [1..{N_m - 1}]")
        else:
            # Squeezing pump, valid indices: k in [-N_m + 1, ..., N_m - 1]
            idx = k + (N_m - 1)
            if 0 <= idx < 2 * N_m - 1:
                gamma[idx] = coeff
            else:
                raise ValueError(f"Squeezing pump index k={k} out of range [-{N_m - 1}..{N_m - 1}]")

    return g, gamma



def build_D_from_allmodes(allmodes_freq, omega0, gamma):
    """
    Constructs a diagonal matrix D of shape (2*nmodes, 2*nmodes),
    where the entries are defined as:

      - for even indices (i = 0, 2, 4, ...):     D[i, i]   = -ω_{-k} - omega0 + iγ/2
      - for odd  indices (i = 1, 3, 5, ...):     D[i+1,i+1] = -ω_{+k} + omega0 + iγ/2

    The array `allmodes_freq` is assumed to be:
      [ω_{-n}, -ω_{-n}, ω_{-(n-1)}, -ω_{-(n-1)}, ..., ω_{-1}, -ω_{-1}]
    representing negative and positive frequency components.
    """
    nm2 = allmodes_freq.size  # Total number of frequencies = 2 * nmodes
    D = np.zeros((nm2, nm2), dtype=complex)
    for i in range(0, nm2, 2):
        ω_minus_k = allmodes_freq[i]
        ω_plus_k  = allmodes_freq[i + 1]
        D[i,   i]   = -ω_minus_k - omega0 + 1j * gamma / 2
        D[i+1, i+1] = -ω_plus_k  + omega0 + 1j * gamma / 2
    return D


    