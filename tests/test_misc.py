import sys
sys.path.insert(0,'src/geometricconvolutions/')

from geometric import (
    geometric_image,
    get_unique_invariant_filters,
    ktensor,
    levi_civita_symbol,
    make_all_operators,
    permutation_parity,
    TINY,
)
import pytest
import jax.numpy as jnp
import jax.random as random
import math

# Now test group actions on k-tensors:
def do_group_actions(operators):
    """
    # Notes:
    - This only does minimal tests!
    """
    D = len(operators[0])
    key = random.PRNGKey(0)

    for parity in [0, 1]:

        key, subkey = random.split(key)

        # vector dot vector
        v1 = ktensor(random.normal(subkey, shape=(D,)), parity, D)
        key, subkey = random.split(key)
        v2 = ktensor(random.normal(subkey, shape=(D,)), parity, D)
        dots = [(v1.times_group_element(gg)
                 * v2.times_group_element(gg)).contract(0, 1).data
                for gg in operators]
        dots = jnp.array(dots)
        if not jnp.allclose(dots, jnp.mean(dots)):
            print("failed (parity = {}) vector dot test.".format(parity))
            return False
        print("passed (parity = {}) vector dot test.".format(parity))

        # tensor times tensor
        key, subkey = random.split(key)
        T3 = ktensor(random.normal(subkey, shape=(D, D)), parity, D)
        key, subkey = random.split(key)
        T4 = ktensor(random.normal(subkey, shape=(D, D)), parity, D)
        dots = [(T3.times_group_element(gg)
                 * T4.times_group_element(gg)).contract(1, 2).contract(0, 1).data
                for gg in operators]
        dots = jnp.array(dots)
        if not jnp.allclose(dots, jnp.mean(dots)):
            print("failed (parity = {}) tensor times tensor test".format(parity))
            return False
        print("passed (parity = {}) tensor times tensor test".format(parity))

        # vectors dotted through tensor
        key, subkey = random.split(key)
        v5 = ktensor(random.normal(subkey, shape=(D,)), 0, D)
        dots = [(v5.times_group_element(gg) * T3.times_group_element(gg)
                 * v2.times_group_element(gg)).contract(1, 2).contract(0, 1).data
                for gg in operators]
        dots = jnp.array(dots)
        if not jnp.allclose(dots, jnp.mean(dots)):
            print("failed (parity = {}) v T v test.".format(parity))
            return False
        print("passed (parity = {}) v T v test.".format(parity))

    return True

class TestMisc:

    def testPermutationParity(self):
        assert permutation_parity([0]) == 1
        assert permutation_parity((0,1)) == 1
        assert permutation_parity((1,0)) == -1
        assert permutation_parity([1,0]) == -1
        assert permutation_parity([1,1]) == 0
        assert permutation_parity([0,1,2]) == 1
        assert permutation_parity([0,2,1]) == -1
        assert permutation_parity([1,2,0]) == 1
        assert permutation_parity([1,0,2]) == -1
        assert permutation_parity([2,1,0]) == -1
        assert permutation_parity([2,0,1]) == 1
        assert permutation_parity([2,1,1]) == 0

    def testLeviCivitaSymbol(self):
        with pytest.raises(AssertionError):
            levi_civita_symbol.get(1)

        assert (levi_civita_symbol.get(2) == jnp.array([[0, 1], [-1, 0]], dtype=int)).all()
        assert (levi_civita_symbol.get(3) == jnp.array(
            [
                [[0,0,0], [0,0,1], [0,-1,0]],
                [[0,0,-1], [0,0,0], [1,0,0]],
                [[0,1,0], [-1,0,0], [0,0,0]],
            ],
            dtype=int)).all()

        assert levi_civita_symbol.get(2) is levi_civita_symbol.get(2) #test that we aren't remaking them

    def testGroupSize(self):
        for d in range(2,7):
            operators = make_all_operators(d)

            # test the group size
            assert len(operators) == 2*(2**(d-1))*math.factorial(d)

    def testGroup(self):
        for d in [2,3]: #could go longer, but it gets slow to test the closure
            operators = make_all_operators(d)
            D = len(operators[0])
            # Check that the list of group operators is closed, O(d^3)
            for gg in operators:
                for gg2 in operators:
                    product = (gg @ gg2).astype(int)
                    found = False
                    for gg3 in operators:
                        if jnp.allclose(gg3, product):
                            found = True
                            break

                    assert found

            # Check that gg.T is gg.inv for all gg in group
            for gg in operators:
                assert jnp.allclose(gg @ gg.T, jnp.eye(D))

            assert do_group_actions(operators)

    def testUniqueInvariantFilters(self):
        # ensure that all the filters are actually invariant
        key = random.PRNGKey(0)

        for D in [2]: #image dimension
            operators = make_all_operators(D)
            for N in [3]: #filter size
                key, subkey = random.split(key)
                image = geometric_image(random.uniform(key, shape=(2*N,2*N)), 0, D)
                for k in [0,1,2]: #tensor order of filter
                    for parity in [0,1]:
                        filters = get_unique_invariant_filters(N, k, parity, D, operators)

                        for gg in operators:
                            for geom_filter in filters:

                                # test that the filters are invariant to the group operators
                                assert jnp.allclose(geom_filter.data, geom_filter.times_group_element(gg).data)

                                # test that the convolution with the invariant filters is equivariant to gg
                                # convolutions are currently too slow to test this every time, but should be tested
                                assert jnp.allclose(
                                    image.convolve_with(geom_filter).times_group_element(gg).data,
                                    image.times_group_element(gg).convolve_with(geom_filter).data,
                                )
