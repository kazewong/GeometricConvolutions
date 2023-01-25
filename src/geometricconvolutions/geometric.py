"""
# Core code for GeometricConvolutions

## License:
Copyright 2022 David W. Hogg and contributors.
The code in GeometricConvolutions is licensed under the open-source MIT License.
See the file `LICENSE` for more details.

## Authors:
- David W. Hogg (NYU)
- Wilson Gregory (JHU)

## To-do items:
- Fix the norm() operations so they are makeable with index summations! Duh. sqrt(a_hij a_hij / d^(k-2)) maybe??
- Move over to jax.
- Create tests for group operations on k-tensor images.
- Fix sizing of multi-filter plots.
- Switch over to jax so this is useful for ML people.
- Need to implement index permutation operation.
- Need to build tests for the contractions.
- Need to implement bin-down and bin-up operators.
"""

import itertools as it
import numpy as np #removing this
import jax.numpy as jnp
import jax.lax
import jax.nn
from jax import jit
from jax.tree_util import register_pytree_node_class
from functools import partial

TINY = 1.e-5
LETTERS = 'abcdefghijklmnopqrstuvwxyxABCDEFGHIJKLMNOPQRSTUVWXYZ'

# ------------------------------------------------------------------------------
# PART 1: Make and test a complete group

def permutation_matrix_from_sequence(seq):
    """
    Give a sequence tuple, return the permutation matrix for that sequence
    """
    D = len(seq)
    permutation_matrix = []
    for num in seq:
        row = [0]*D
        row[num] = 1
        permutation_matrix.append(row)
    return jnp.array(permutation_matrix)

def make_all_operators(D):
    """
    Construct all operators of dimension D that are rotations of 90 degrees, or reflections, or a combination of the
    two. This is equivalent to all the permutation matrices where each entry can either be +1 or -1
    args:
        D (int): dimension of the operator
    """

    # permutation matrices, one for each permutation of length D
    permutation_matrices = [permutation_matrix_from_sequence(seq) for seq in it.permutations(range(D))]
    # possible entries, e.g. for D=2: (1,1), (-1,1), (1,-1), (-1,-1)
    possible_entries = [np.diag(prod) for prod in it.product([1,-1], repeat=D)]

    #combine all the permutation matrices with the possible entries, then flatten to a single array of operators
    return list(it.chain(*list(map(lambda matrix: [matrix @ prod for prod in possible_entries], permutation_matrices))))


# ------------------------------------------------------------------------------
# PART 1.5: Define the Kronecker Delta and Levi Civita symbols to be used in Levi Civita contractions

class KroneckerDeltaSymbol:
    #we only want to create each dimension of levi civita symbol once, so we cache them in this dictionary
    symbol_dict = {}

    @classmethod
    def get(cls, D, k):
        """
        Get the Levi Civita symbol for dimension D from the cache, or creating it on a cache miss
        args:
            D (int): dimension of the Kronecker symbol
            k (int): order of the Kronecker Delta symbol
        """
        assert D > 1
        assert k > 1
        if (D,k) not in cls.symbol_dict:
            arr = np.zeros((k * (D,)), dtype=int)
            for i in range(D):
                arr[(i,)*k] = 1
            cls.symbol_dict[(D,k)] = arr

        return cls.symbol_dict[(D,k)]

    @classmethod
    def get_image(cls, N, D, k):
        return GeometricImage(jnp.stack([cls.get(D,k) for _ in range(N**D)]).reshape(((N,)*D + (D,)*k)), 0, D)

def permutation_parity(pi):
    """
    Code taken from Sympy Permutations: https://github.com/sympy/sympy/blob/26f7bdbe3f860e7b4492e102edec2d6b429b5aaf/sympy/combinatorics/permutations.py#L114
    Slightly modified to return 1 for even permutations, -1 for odd permutations, and 0 for repeated digits
    Permutations of length n must consist of numbers {0, 1, ..., n-1}
    """
    if (len(np.unique(pi)) != len(pi)):
        return 0

    n = len(pi)
    a = [0] * n
    c = 0
    for j in range(n):
        if a[j] == 0:
            c += 1
            a[j] = 1
            i = j
            while pi[i] != j:
                i = pi[i]
                a[i] = 1

    # code originally returned 1 for odd permutations (we want -1) and 0 for even permutations (we want 1)
    return -2*((n - c) % 2)+1

class LeviCivitaSymbol:

    #we only want to create each dimension of levi civita symbol once, so we cache them in this dictionary
    symbol_dict = {}

    @classmethod
    def get(cls, D):
        """
        Get the Levi Civita symbol for dimension D from the cache, or creating it on a cache miss
        args:
            D (int): dimension of the Levi Civita symbol
        """
        assert D > 1
        if D not in cls.symbol_dict:
            arr = np.zeros((D * (D,)), dtype=int)
            for index in it.product(range(D), repeat=D):
                arr[index] = permutation_parity(index)
            cls.symbol_dict[D] = jnp.array(arr)

        return cls.symbol_dict[D]



# ------------------------------------------------------------------------------
# PART 4: Use group averaging to find unique invariant filters.

def get_unique_invariant_filters(M, k, parity, D, operators, scale='normalize'):
    """
    Use group averaging to generate all the unique invariant filters
    args:
        M (int): filter side length
        k (int): tensor order
        parity (int):  0 or 1, 0 is for normal tensors, 1 for pseudo-tensors
        D (int): image dimension
        operators (jnp-array): array of operators of a group
        scale (string): option for scaling the values of the filters, 'normalize' (default) to make amplitudes of each
        tensor +/- 1. 'one' to set them all to 1.
    """
    assert scale == 'normalize' or scale == 'one'

    # make the seed filters
    tmp = GeometricFilter.zeros(M, k, parity, D)
    keys, shape = tmp.keys(), tmp.data.shape
    allfilters = []
    if k == 0:
        for kk in keys:
            thisfilter = GeometricFilter.zeros(M, k, parity, D)
            thisfilter[kk] = 1
            allfilters.append(thisfilter)
    else:
        for kk in keys:
            thisfilter = GeometricFilter.zeros(M, k, parity, D)
            for indices in it.product(range(D), repeat=k):
                thisfilter[kk] = thisfilter[kk].at[indices].set(1) #is this even right?
                allfilters.append(thisfilter)

    # do the group averaging
    bigshape = (len(allfilters), ) + thisfilter.data.flatten().shape
    filter_matrix = np.zeros(bigshape)
    for i, f1 in enumerate(allfilters):
        ff = GeometricFilter.zeros(M, k, parity, D)
        for gg in operators:
            ff = ff + f1.times_group_element(gg)
        filter_matrix[i] = ff.data.flatten()

    # do the SVD
    u, s, v = np.linalg.svd(filter_matrix)
    sbig = s > TINY
    if not np.any(sbig):
        return []

    # normalize the amplitudes so they max out at +/- 1.
    amps = v[sbig] / np.max(np.abs(v[sbig]), axis=1)[:, None]
    # make sure the amps are positive, generally
    for i in range(len(amps)):
        if np.sum(amps[i]) < 0:
            amps[i] *= -1
    # make sure that the zeros are zeros.
    amps[np.abs(amps) < TINY] = 0.

    # order them
    filters = [GeometricFilter(aa.reshape(shape), parity, D) for aa in amps]
    if (scale == 'normalize'):
        filters = [ff.normalize() for ff in filters]

    norms = [ff.bigness() for ff in filters]
    I = np.argsort(norms)
    filters = [filters[i] for i in I]

    # now do k-dependent rectification:
    filters = [ff.rectify() for ff in filters]

    return filters

def get_invariant_filters(Ms, ks, parities, D, operators, scale='normalize', return_list=False, return_maxn=False):
    """
    Use group averaging to generate all the unique invariant filters for the ranges of Ms, ks, and parities. By default
    it returns the filters in a dictionary with the key (D,M,k,parity), but flattens to a list if return_list=True
    args:
        Ms (iterable of int): filter side lengths
        ks (iterable of int): tensor orders
        parities (iterable of int):  0 or 1, 0 is for normal tensors, 1 for pseudo-tensors
        D (int): image dimension
        operators (jnp-array): array of operators of a group
        scale (string): option for scaling the values of the filters, 'normalize' (default) to make amplitudes of each
        tensor +/- 1. 'one' to set them all to 1.
        return_list (bool): defaults to False, if true return allfilters as a list
        return_maxn (bool): defaults to False, if true returns the length of the max list for each D, M
    returns:
        allfilters: a dictionary of filters of the specified D, M, k, and parity. If return_list=True, this is a list
        maxn: a dictionary that tracks the longest number of filters per key, for a particular D,M combo. Not returned
            if return_list=True
    """
    assert scale == 'normalize' or scale == 'one'

    allfilters = {}
    maxn = {}
    for M in Ms: #filter side length
        maxn[(D, M)] = 0
        for k in ks: #tensor order
            for parity in parities: #parity
                key = (D, M, k, parity)
                allfilters[key] = get_unique_invariant_filters(M, k, parity, D, operators, scale)
                n = len(allfilters[key])
                if n > maxn[(D, M)]:
                    maxn[(D, M)] = n

    if return_list:
        allfilters = list(it.chain(*list(allfilters.values())))

    if return_maxn:
        return allfilters, maxn
    else:
        return allfilters


# ------------------------------------------------------------------------------
# PART 5: Define geometric (k-tensor, torus) images.

def get_contraction_indices(initial_k, final_k):
    """
    Get all possible unique indices for multicontraction. Returns a list of indices. The indices are a tuple of tuples
    where each of the inner tuples are pairs of indices. For example, if initial_k=5, final_k = 4, one element of the
    list that is returned will be ((0,1), (2,3)), another will be ((1,4), (0,2)), etc.

    Note that contracting (0,1) is the same as contracting (1,0). Also, contracting ((0,1),(2,3)) is the same as
    contracting ((2,3),(0,1)). In both of those cases, they won't be returned. There are additional contractions that
    are the same depending on how the image was created, but we don't worry about that complexity here.
    args:
        initial_k (int): the starting number of indices that we have
        final_k (int): the final number of indices that we want to end up with
    """
    assert ((initial_k + final_k) % 2)  == 0
    assert initial_k >= final_k
    assert final_k >= 0
    tuple_pairs = it.combinations(it.combinations(range(initial_k),2),(initial_k - final_k) // 2)
    pairs = np.array([np.array(pair).reshape((initial_k - final_k,)) for pair in tuple_pairs])
    unique_rows = np.array([True if len(np.unique(row)) == len(row) else False for row in pairs])
    unique_pairs = pairs[unique_rows]
    return [tuple((x,y) for x,y in zip(idxs[0::2], idxs[1::2])) for idxs in unique_pairs]

@partial(jit, static_argnums=1)
def multicontract(data, indices):
    """
    Perform the Kronecker Delta contraction on the data. Must have at least 2 dimensions, and because we implement with
    einsum, must have at most 52 dimensions. Indices a tuple of pairs of indices, also tuples.
    args:
        data (np.array-like): data to perform the contraction on
        indices (tuple of tuples of ints): index pairs to perform the contractions on
    """
    dimensions = len(data.shape)
    assert dimensions + len(indices) < 52
    assert dimensions >= 2
    #all indices must be unique, indices must be greater than 0 and less than dimensions

    einstr = list(LETTERS[:dimensions])
    for i, (idx1, idx2) in enumerate(indices):
        einstr[idx1] = einstr[idx2] = LETTERS[-(i+1)]

    return jnp.einsum(''.join(einstr), data)

@jit
def linear_combination(images, params):
    """
    A method takes a list of parameters, a list of geometric images and returns the linear combination.
    The images must all have the same k, and the likely should have the same parity.
    args:
        images (list): list of GeometricImages to be multiplied by the params, then summed
        params (list): scalar multipliers of the images
    """
    assert len(images) == len(params) #must be the same length

    data = jnp.sum(jnp.array([image.data * param for image, param in zip(images, params)]), axis=0)
    return images[0].__class__(data, images[0].parity, images[0].D)

def tensor_name(k, parity):
    nn = "tensor"
    if k == 0:
        nn = "scalar"
    if k == 1:
        nn = "vector"
    if parity % 2 == 1 and k < 2:
        nn = "pseudo" + nn
    if k > 1:
        nn = "${}$-${}$-".format(k, parity) + nn
    return nn

@register_pytree_node_class
class GeometricImage:

    # Constructors

    @classmethod
    def zeros(cls, N, k, parity, D):
        """
        Class method zeros to construct a geometric image of zeros
        args:
            N (int): length of a side of an image, currently all images must be square N^D pixels
            k (int): the order of the tensor in each pixel, i.e. 0 (scalar), 1 (vector), 2 (matrix), etc.
            parity (int): 0 or 1, 0 is normal vectors, 1 is pseudovectors
            D (int): dimension of the image, and length of vectors or side length of matrices or tensors.
        """
        shape = D * (N, ) + k * (D, )
        return cls(jnp.zeros(shape), parity, D)

    @classmethod
    def fill(cls, N, parity, D, fill):
        """
        Class method fill constructor to construct a geometric image every pixel as fill
        args:
            N (int): length of a side of an image, currently all images must be square N^D pixels
            parity (int): 0 or 1, 0 is normal vectors, 1 is pseudovectors
            D (int): dimension of the image, and length of vectors or side length of matrices or tensors.
            fill (jnp.ndarray or number): tensor to fill the image with
        """
        k = len(fill.shape) if isinstance(fill, jnp.ndarray) else 0
        data = jnp.stack([fill for _ in range(N ** D)]).reshape((N,)*D + (D,)*k)
        return cls(data, parity, D)

    def __init__(self, data, parity, D):
        """
        Construct the GeometricImage. It will be (N^D x D^k), so if N=100, D=2, k=1, then it's (100 x 100 x 2)
        args:
            data (array-like):
            parity (int): 0 or 1, 0 is normal vectors, 1 is pseudovectors
            D (int): dimension of the image, and length of vectors or side length of matrices or tensors.
        """
        self.D = D
        self.N = len(data)
        self.k = len(data.shape) - D
        assert data.shape[:D] == self.D * (self.N, ), \
        "GeometricImage: data must be square."
        assert data.shape[D:] == self.k * (self.D, ), \
        "GeometricImage: each pixel must be D cross D, k times"
        self.parity = parity % 2
        self.data = jnp.copy(data) #TODO: don't need to copy if data is already an immutable jnp array

    def copy(self):
        return self.__class__(self.data, self.parity, self.D)

    # Getters, setters, basic info

    def hash(self, indices):
        """
        Deals with torus by modding (with `np.remainder()`).
        args:
            indices (tuple of ints): indices to apply the remainder to
        """
        return tuple(jnp.remainder(indices, self.N).transpose().astype(int))

    def __getitem__(self, key):
        """
        Accessor for data values. Now you can do image[key] where k are indices or array slices and it will just work
        Note that JAX does not throw errors for indexing out of bounds
        args:
            key (index): JAX/numpy indexer, i.e. "0", "0,1,3", "4:, 2:3, 0" etc.
        """
        return self.data[key]

    def __setitem__(self, key, val):
        """
        Jax arrays are immutable, so this reconstructs the data object with copying, and is potentially slow
        """
        self.data = self.data.at[key].set(val)
        return self

    def shape(self):
        """
        Return the full shape of the data block
        """
        return self.data.shape

    def image_shape(self):
        """
        Return the shape of the data block that is not the ktensor shape, but what comes before that. For regular
        GeometricImages, this is shape of the literal image. For BatchGeometricImage it prepends the batch size L.
        """
        return self.D*(self.N,)

    def pixel_shape(self):
        """
        Return the shape of the data block that is the ktensor, aka the pixel of the image.
        """
        return self.k*(self.D,)

    def pixel_size(self):
        """
        Get the size of the pixel shape, i.e. (D,D,D) = D**3
        """
        return self.D ** self.k

    def __str__(self):
        return "<{} object in D={} with N={}, k={}, and parity={}>".format(
            self.__class__, self.D, self.N, self.k, self.parity)

    def keys(self):
        """
        Iterate over the keys of GeometricImage
        """
        return it.product(range(self.N), repeat=self.D)

    def key_array(self):
        # equivalent to the old pixels function
        return jnp.array([key for key in self.keys()], dtype=int)

    def pixels(self):
        """
        Iterate over the pixels of GeometricImage.
        """
        for key in self.keys():
            yield self[key]

    def items(self):
        """
        Iterate over the key, pixel pairs of GeometricImage.
        """
        for key in self.keys():
            yield (key, self[key])

    # Binary Operators, Complicated functions

    def __eq__(self, other):
        """
        Equality operator, must have same shape, parity, and data within the TINY=1e-5 tolerance.
        """
        return (
            self.D == other.D and
            self.N == other.N and
            self.k == other.k and
            self.parity == other.parity and
            self.data.shape == other.data.shape and
            jnp.allclose(self.data, other.data, rtol=TINY, atol=TINY)
        )

    def __add__(self, other):
        """
        Addition operator for GeometricImages. Both must be the same size and parity. Returns a new GeometricImage.
        args:
            other (GeometricImage): other image to add the the first one
        """
        assert self.D == other.D
        assert self.N == other.N
        assert self.k == other.k
        assert self.parity == other.parity
        assert self.data.shape == other.data.shape
        return self.__class__(self.data + other.data, self.parity, self.D)

    def __sub__(self, other):
        """
        Subtraction operator for GeometricImages. Both must be the same size and parity. Returns a new GeometricImage.
        args:
            other (GeometricImage): other image to add the the first one
        """
        assert self.D == other.D
        assert self.N == other.N
        assert self.k == other.k
        assert self.parity == other.parity
        assert self.data.shape == other.data.shape
        return self.__class__(self.data - other.data, self.parity, self.D)

    def __mul__(self, other):
        """
        If other is a scalar, do scalar multiplication of the data. If it is another GeometricImage, do the tensor
        product at each pixel. Return the result as a new GeometricImage.
        args:
            other (GeometricImage or number): scalar or image to multiply by
        """
        if (isinstance(other, GeometricImage)):
            assert self.D == other.D
            assert self.N == other.N
            image_a_data, image_b_data = GeometricImage.pre_tensor_product_expand(self, other)
            #now that the shapes match, we can do elementwise multiplication
            return self.__class__(image_a_data * image_b_data, self.parity + other.parity, self.D)
        else: #its an integer or a float, or something that can we can multiply a Jax array by (like a DeviceArray)
            return self.__class__(self.data * other, self.parity, self.D)

    def __rmul__(self, other):
        """
        If other is a scalar, multiply the data by the scalar. This is necessary for doing scalar * image, and it
        should only be called in that case.
        """
        return self * other

    def transpose(self, axes_permutation):
        """
        Transposes the axes of the tensor, keeping the image axes in the front the same
        args:
            axes_permutation (iterable of indices): new axes order
        """
        idx_shift = len(self.image_shape())
        new_indices = tuple(tuple(range(idx_shift)) + tuple(axis + idx_shift for axis in axes_permutation))
        return self.__class__(jnp.transpose(self.data, new_indices), self.parity, self.D)

    @classmethod
    def pre_tensor_product_expand(cls, image_a, image_b):
        """
        Rather than take a tensor product of two tensors, we can first take a tensor product of each with a tensor of
        ones with the shape of the other. Then we have two matching shapes, and we can then do whatever operations.
        This is a class method that takes in two images and returns the expanded data
        args:
            image_a (GeometricImage like): one geometric image whose tensors we will later be doing tensor products on
            image_b (GeometricImage like): other geometric image
        """
        if (len(image_b.pixel_shape())):
            image_a_expanded = jnp.tensordot(
                image_a.data,
                jnp.ones(image_b.pixel_shape()),
                axes=0,
            )
        else:
            image_a_expanded = image_a.data

        if len(image_a.pixel_shape()):
            break1 = image_a.k + len(image_b.image_shape()) #after outer product, end of image_b N^D axes
            #after outer product: [D^ki, N^D, D^kf], convert to [N^D, D^ki, D^kf]
            # we are trying to expand the ones in the middle (D^ki), so we add them on the front, then move to middle
            image_b_expanded = jnp.transpose(
                jnp.tensordot(jnp.ones(image_a.pixel_shape()), image_b.data, axes=0),
                list(
                    tuple(range(image_a.k, break1)) + tuple(range(image_a.k)) + tuple(range(break1, break1 + image_b.k))
                ),
            )
        else:
            image_b_expanded = image_b.data

        return image_a_expanded, image_b_expanded

    @classmethod
    def data_to_NHWC_format(cls, image_data, image_shape, channel_length):
        """
        Given image data, format it into the NHWC format that is used by the convolution function. For GeometricImage
        we need to prepend the 1 because that is the batch size.
        args:
            image_data (jnp.array): array of data, after torus expanding, stretching to match the filter
            image_shape (tuple of ints): output of torus_expand.image_shape()
            channel_length (int): the size of the output ktensor, we are vectorizing it
        """
        return image_data.reshape((1,) + image_shape + (channel_length,))

    @jit
    def convolve_with(self, filter_image, warnings=True):
        """
        Here is how this function works:
        1. Expand the geom_image to its torus shape, i.e. add filter.m cells all around the perimeter of the image
        2. Do the tensor product (with 1s) to each image.k, filter.k so that they are both image.k + filter.k tensors.
        That is if image.k=2, filter.k=1, do (D,D) => (D,D) x (D,) and (D,) => (D,D) x (D,) with tensors of 1s
        3. Now we shape the inputs to work with jax.lax.conv_general_dilated
        4. Put image in NHWC (batch, height, width, channel). Thus we vectorize the tensor
        5. Put filter in HWIO (height, width, input, output). Input is 1, output is the vectorized tensor
        6. Plug all that stuff in to conv_general_dilated, and feature_group_count is the length of the vectorized
        tensor, and it is basically saying that each part of the vectorized tensor is treated separately in the filter.
        It must be the case that channel = input * feature_group_count
        See: https://jax.readthedocs.io/en/latest/notebooks/convolutions.html#id1 and
        https://www.tensorflow.org/xla/operation_semantics#conv_convolution

        args:
            filter_image (GeometricFilter): the filter we are performing the convolution with
            warnings (bool): display warnings, defaults to True currently
        """
        if (self.data.dtype != filter_image.data.dtype):
            dtype = 'float32'
            if (warnings):
                print('GeometricImage::convolve_with: GeometricImage dtype and filter_image dtype mismatch, converting to float32')
        else:
            dtype = self.data.dtype

        output_k = self.k + filter_image.k
        torus_expand_img = self.get_torus_expanded(filter_image)

        img_expanded, filter_expanded = GeometricImage.pre_tensor_product_expand(torus_expand_img, filter_image)
        img_expanded = img_expanded.astype(dtype)
        filter_expanded = filter_expanded.astype(dtype)

        channel_length = int(np.multiply.reduce(self.pixel_shape() + filter_image.pixel_shape()))

        # convert the image to NHWC (or NHWDC), treating all the pixel values as channels
        img_formatted = self.__class__.data_to_NHWC_format(
            img_expanded,
            torus_expand_img.image_shape(),
            channel_length,
        )

        # convert filter to HWIO (or HWDIO)
        filter_formatted = filter_expanded.reshape(filter_image.image_shape() + (1,channel_length))

        if self.D == 2:
            dimension_numbers = ('NHWC','HWIO','NHWC')
            window_strides = (1,1)
        elif self.D == 3:
            dimension_numbers = ('NHWDC','HWDIO','NHWDC')
            window_strides = (1,1,1)

        convolved_array = jax.lax.conv_general_dilated(
            img_formatted, #lhs
            filter_formatted, #rhs
            window_strides, #window strides
            'VALID', #padding mode, we can do valid because we already expanded on the torus
            dimension_numbers=dimension_numbers,
            feature_group_count=channel_length, #allows us to have separate filters for separate channels
        ).reshape(self.image_shape() + (self.D,)*output_k) #reshape the pixel to the correct tensor shape
        return self.__class__(convolved_array, self.parity + filter_image.parity, self.D)

    def get_torus_expanded(self, filter_image):
        """
        For a particular filter, expand the image so that we no longer have to do convolutions on the torus, we are
        just doing convolutions on the expanded image and will get the same result. Return a new GeometricImage
        args:
            filter_image (GeometricFilter): filter, how much is expanded depends on filter_image.m
        """
        new_N = self.N + 2 * filter_image.m
        indices = jnp.array(list(it.product(range(new_N), repeat=self.D)), dtype=int) - filter_image.m
        return self.__class__(
            self[self.hash(indices)].reshape((new_N,) * self.D + self.pixel_shape()),
            self.parity,
            self.D,
        )

    def times_scalar(self, scalar):
        """
        Scale the data by a scalar, returning a new GeometricImage object. Alias of the multiplication operator.
        args:
            scalar (number): number to scale everything by
        """
        return self * scalar

    def norm(self):
        """
        Calculate the norm pixel-wise
        """
        if self.k == 0:
            return jnp.abs(self.data)

        image_size = int(np.multiply.reduce(self.image_shape()))
        vectorized_pixels = self.data.reshape(((image_size,) + self.pixel_shape()))
        return jnp.array([jnp.linalg.norm(x, ord=None) for x in vectorized_pixels]).reshape(self.image_shape())

    def normalize(self):
        """
        Normalize so that the max norm of each pixel is 1, and all other tensors are scaled appropriately
        """
        max_norm = jnp.max(self.norm())
        if max_norm > TINY:
            return self.times_scalar(1. / max_norm)
        else:
            return self.times_scalar(1.)

    def activation_function(self, function):
        assert self.k == 0, "Activation functions only implemented for k=0 tensors due to equivariance"
        return self.__class__(function(self.data), self.parity, self.D)

    @partial(jit, static_argnums=[1,2])
    def contract(self, i, j):
        """
        Use einsum to perform a kronecker contraction on two dimensions of the tensor
        args:
            i (int): first index of tensor
            j (int): second index of tensor
        """
        assert self.k >= 2
        idx_shift = len(self.image_shape())
        return self.__class__(
            multicontract(self.data, ((i + idx_shift, j + idx_shift),)),
            self.parity,
            self.D,
        )

    @partial(jit, static_argnums=1)
    def multicontract(self, indices):
        """
        Use einsum to perform a kronecker contraction on two dimensions of the tensor
        args:
            indices (tuple of tuples of ints): indices to contract
        """
        assert self.k >= 2
        idx_shift = len(self.image_shape())
        shifted_indices = tuple((i + idx_shift, j + idx_shift) for i,j in indices)
        return self.__class__(multicontract(self.data, shifted_indices), self.parity, self.D)

    def levi_civita_contract(self, indices):
        """
        Perform the Levi-Civita contraction. Outer product with the Levi-Civita Symbol, then perform D-1 contractions.
        Resulting image has k= self.k - self.D + 2
        args:
            indices (int, or tuple, or list): indices of tensor to perform contractions on
        """
        assert self.k >= (self.D - 1) # so we have enough indices to work on since we perform D-1 contractions
        if self.D == 2 and not (isinstance(indices, tuple) or isinstance(indices, list)):
            indices = (indices,)
        assert len(indices) == self.D - 1

        levi_civita = LeviCivitaSymbol.get(self.D)
        outer = jnp.tensordot(self.data, levi_civita, axes=0)

        #make contraction index pairs with one of specified indices, and index (in order) from the levi_civita symbol
        idx_shift = len(self.image_shape())
        zipped_indices = tuple((i+idx_shift,j+idx_shift) for i,j in zip(indices, range(self.k, self.k + len(indices))))
        return self.__class__(multicontract(outer, zipped_indices), self.parity + 1, self.D)

    def anticontract(self, additional_k):
        """
        Expand the ktensor so that the new order is self.k + additional_k. Then elemenet-wise multiply it by a
        special symbol such that no matter what contractions you perform to return it to the orignal k, it equals the
        original image. This only works under certain conditions, given by the asserts.
        args:
            additional_k (int): how many dimensions we are adding
        """
        # Currently these are the only cases it works with and has been tested for.
        assert self.k == 0 or self.k == 1
        assert additional_k == 2 or additional_k == 4
        assert self.D == 2

        expanded_data = jnp.tensordot(self.data, jnp.ones((self.D,)*additional_k), axes=0) #stretch the data

        if self.k == 0: # 1 in the [0,0,...,0] position, zeros everywhere else
            kron_delta = jnp.array(list((1,) + (0,)*(self.D**additional_k - 1))).reshape(((self.D,)*additional_k))
        elif self.k == 1:
            kron_delta = KroneckerDeltaSymbol.get(self.D, additional_k + self.k)

        kron_delta = jnp.tensordot(jnp.ones(self.image_shape()), kron_delta, axes=0)

        assert expanded_data.shape == kron_delta.shape

        return self.__class__(expanded_data * kron_delta, self.parity, self.D)

    def get_rotated_keys(self, gg):
        """
        Slightly messier than with GeometricFilter because self.N-1 / 2 might not be an integer, but should work
        args:
            gg (jnp array-like): group operation
        """
        key_array = self.key_array() - ((self.N-1) / 2)
        return jnp.rint((key_array @ gg) + (self.N-1) / 2).astype(int)

    def times_group_element(self, gg):
        """
        Apply a group element of SO(2) or SO(3) to the geometric image. First apply the action to the location of the
        pixels, then apply the action to the pixels themselves.
        args:
            gg (group operation matrix): a DxD matrix that rotates the tensor
        """
        assert self.k < 14
        assert gg.shape == (self.D, self.D)
        sign, logdet = np.linalg.slogdet(gg)
        assert logdet == 0. #determinant is +- 1, so abs(log(det)) should be 0
        parity_flip = sign ** self.parity #if parity=1, the flip operators don't flip the tensors

        rotated_keys = self.get_rotated_keys(gg)
        rotated_pixels = self[self.hash(rotated_keys)].reshape(self.shape())

        if self.k == 0:
            newdata = 1. * rotated_pixels * parity_flip
        else:
            # applying the rotation to tensors is essentially multiplying each index, which we can think of as a
            # vector, by the group action. The image pixels have already been rotated.
            einstr = LETTERS[:len(self.shape())] + ','
            einstr += ",".join([LETTERS[i+13] + LETTERS[i + len(self.image_shape())] for i in range(self.k)])
            tensor_inputs = (rotated_pixels, ) + self.k * (gg, )
            newdata = np.einsum(einstr, *tensor_inputs) * (parity_flip)

        return self.__class__(newdata, self.parity, self.D)

    def tree_flatten(self):
        """
        Helper function to define GeometricImage as a pytree so jax.jit handles it correctly. Children and aux_data
        must contain all the variables that are passed in __init__()
        """
        children = (self.data,)  # arrays / dynamic values
        aux_data = {
            'D': self.D,
            'parity': self.parity,
        }  # static values
        return (children, aux_data)

    @classmethod
    def tree_unflatten(cls, aux_data, children):
        """
        Helper function to define GeometricImage as a pytree so jax.jit handles it correctly.
        """
        return cls(*children, **aux_data)

# ------------------------------------------------------------------------------
# PART 3: Define a geometric (k-tensor) filter.

@register_pytree_node_class
class GeometricFilter(GeometricImage):

    def __init__(self, data, parity, D):
        super(GeometricFilter, self).__init__(data, parity, D)
        self.m = (self.N - 1) // 2
        assert self.N == 2 * self.m + 1, \
        "GeometricFilter: N needs to be odd."

    @classmethod
    def from_image(cls, geometric_image):
        """
        Constructor that copies a GeometricImage and returns a GeometricFilter
        """
        return cls(geometric_image.data, geometric_image.parity, geometric_image.D)

    def __str__(self):
        return "<geometric filter object in D={} with N={} (m={}), k={}, and parity={}>".format(
            self.D, self.N, self.m, self.k, self.parity)

    def bigness(self):
        """
        Gives an idea of size for a filter, sparser filters are smaller while less sparse filters are larger
        """
        norms = self.norm()
        numerator = 0.
        for key in self.key_array():
            numerator += jnp.linalg.norm(key * norms[tuple(key)], ord=2)

        denominator = jnp.sum(norms)
        return numerator / denominator

    def key_array(self, centered=False):
        # equivalent to the old pixels function
        if centered:
            return jnp.array([key for key in self.keys()], dtype=int) - self.m
        else:
            return jnp.array([key for key in self.keys()], dtype=int)

    def keys(self, centered=False):
        """
        Enumerate over all the keys in the geometric filter. Use centered=True when using the keys as adjustments
        args:
            centered (bool): if true, the keys range from -m to m rather than 0 to N. Defaults to false.
        """
        for key in super().keys():
            if (centered):
                #subtract m from all the elements of key
                yield tuple([a+b for a,b in zip(key, len(key) * (-self.m,))])
            else:
                yield key

    def items(self, centered=False):
        """
        Enumerate over all the key, pixel pairs in the geometric filter. Use centered=True when using the keys as
        adjustments
        args:
            centered (bool): if true, the keys range from -m to m rather than 0 to N. Defaults to false.
        """
        for key in self.keys(): #dont pass centered along because we need the un-centered keys to access the vals
            value = self[key]
            if (centered):
                #subtract m from all the elements of key
                yield (tuple([a+b for a,b in zip(key, len(key) * (-self.m,))]), value)
            else:
                yield (key, value)

    def get_rotated_keys(self, gg):
        key_array = self.key_array(centered=True)
        return (key_array @ gg) + self.m

    def rectify(self):
        """
        Filters form an equivalence class up to multiplication by a scalar, so if its negative we want to flip the sign
        """
        if self.k == 0:
            if jnp.sum(self.data) < 0:
                return self.times_scalar(-1)
        elif self.k == 1:
            if self.parity % 2 == 0:
                if np.sum([np.dot(np.array(key), self[key]) for key in self.keys()]) < 0:
                    return self.times_scalar(-1)
            elif self.D == 2:
                if np.sum([np.cross(np.array(key), self[key]) for key in self.keys()]) < 0:
                    return self.times_scalar(-1)
        return self

@register_pytree_node_class
class BatchGeometricImage(GeometricImage):
    """
    A GeometricImage class where the data is actually L geometric images
    """

    # Constructors

    @classmethod
    def fill(cls, N, parity, D, fill, L):
        """
        Class method fill constructor to construct a geometric image every pixel as fill
        args:
            N (int): length of a side of an image, currently all images must be square N^D pixels
            parity (int): 0 or 1, 0 is normal vectors, 1 is pseudovectors
            D (int): dimension of the image, and length of vectors or side length of matrices or tensors.
            fill (jnp.ndarray or number): tensor to fill the image with
        """
        k = len(fill.shape) if isinstance(fill, jnp.ndarray) else 0
        data = jnp.stack([fill for _ in range(L * (N ** D))]).reshape((L,) + (N,)*D + (D,)*k)
        return cls(data, parity, D)

    def __init__(self, data, parity, D):
        """
        Construct the GeometricImage. It will be (L x N^D x D^k), so if L=16, N=100, D=2, k=1, then it's
        (16 x 100 x 100 x 2)
        args:
            data (array-like): the data
            parity (int): 0 or 1, 0 is normal vectors, 1 is pseudovectors
            D (int): dimension of the image, and length of vectors or side length of matrices or tensors.
        """
        super(BatchGeometricImage, self).__init__(data[0], parity, D)
        self.L = data.shape[0]
        self.data = data

    @classmethod
    def from_images(cls, images, indices=None):
        """
        Class method to construct a BatchGeometricImage from a list of GeometricImages. All the images should have the
        same parity, D, and k.
        args:
            images (list of GeometricImages): images that we are making into a batch image
        """
        if indices is None:
            indices = range(len(images))
            
        return cls(jnp.stack([images[idx].data for idx in indices]), images[0].parity, images[0].D)

    def image_shape(self):
        """
        Return the shape of the data block that is not the ktensor shape, but what comes before that. For regular
        GeometricImages, this is shape of the literal image. For BatchGeometricImage it prepends the batch size L.
        """
        return (self.L,) + (self.N,) * self.D

    def __str__(self):
        return "<{} object with L={} images in D={} with N={}, k={}, and parity={}>".format(
            self.__class__, self.L, self.D, self.N, self.k, self.parity)

    # Binary Operators, Complicated functions

    def __eq__(self, other):
        """
        Equality operator, must have same L, shape, parity, and data within the TINY=1e-5 tolerance.
        """
        return self.L == other.L and super(BatchGeometricImage, self).__eq__(other)

    def __mul__(self, other):
        """
        Multiplication operator for BatchGeometricImages. Both must have the same batch size.
        args:
            other (GeometricImage or number): scalar or image to multiply by
        """
        assert self.L == other.L
        return super(BatchGeometricImage, self).__mul__(other)

    @classmethod
    def data_to_NHWC_format(cls, image_data, image_shape, channel_length):
        """
        Given image data, format it into the NHWC format that is used by the convolution function. For
        BatchGeometricImage we don't need to prepend the 1 because we already have the batch size in image_shape
        args:
            image_data (jnp.array): array of data, after torus expanding, stretching to match the filter
            image_shape (tuple of ints): output of torus_expand.image_shape()
            channel_length (int): the size of the output ktensor, we are vectorizing it
        """
        return image_data.reshape(image_shape + (channel_length,))

    def get_torus_expanded(self, filter_image):
        """
        For a particular filter, expand the image so that we no longer have to do convolutions on the torus, we are
        just doing convolutions on the expanded image and will get the same result. Return a new GeometricImage
        args:
            filter_image (GeometricFilter): filter, how much is expanded depends on filter_image.m
        """
        new_N = self.N + 2 * filter_image.m
        indices = jnp.array(list(it.product(range(new_N), repeat=self.D)), dtype=int) - filter_image.m
        flipped_data = jnp.moveaxis(self.data, 0, -1) #flip batch axis to the end
        indexed_data = jnp.moveaxis(flipped_data[self.hash(indices)], -1, 0) #flip batch axis back to the front

        return self.__class__(
            indexed_data.reshape((self.L,) + (new_N,) * self.D + self.pixel_shape()),
            self.parity,
            self.D,
        )

    # TODO!!
    def normalize(self):
        raise Exception('BatchGeometricImage::normalize is not implemented')
